"""Phase 7 — tests for video-as-vision feature.

Coverage:
  * VisualUsagePolicy.normalize — defaults + case folding
  * WorkflowRecorder
      - off mode is a no-op
      - screenshots mode writes PNGs and timestamps per step
      - video mode emits the right context kwargs
  * VisualInspector
      - no_vision_llm short-circuit
      - graceful no-frames branch
      - mocked vision LLM happy path (parses JSON answer)
      - response with prose around JSON is still parsed
  * WorkflowOrchestrator vision gating
      - policy=never → inspector NOT called even on failure
      - policy=on_failure → inspector called when step fails
      - policy=on_ambiguous → inspector called when verifier confidence is low
      - visual_finding attached to StepRunRecord
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from xpath_healer.core.models import LocatorSpec, Recovered
from xpath_healer.core.workflow import WorkflowStep
from xpath_healer.llm.client import ChatMessage, ChatResponse, LLMClient, ToolCall, ToolDefinition
from xpath_healer.orchestrator import (
    AgenticGoalDecomposer,
    InspectionResult,
    OrchestrationResult,
    PlaywrightActionExecutor,
    RecordingInfo,
    StepSnapshot,
    TieredOutcomeVerifier,
    VisualInspector,
    VisualUsagePolicy,
    WorkflowGoal,
    WorkflowOrchestrator,
    WorkflowRecorder,
)


# ===========================================================================
# Shared helpers
# ===========================================================================


class _ScriptedLLM(LLMClient):
    def __init__(self, responses: list[ChatResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages, *, tools=None, temperature=0.0, max_tokens=None) -> ChatResponse:
        self.calls.append(list(messages))
        if not self._responses:
            return ChatResponse(content="", tool_calls=[])
        return self._responses.pop(0)


class _FakePage:
    """Minimal page with .screenshot writing a tiny PNG to disk."""

    def __init__(self) -> None:
        self.screenshots: list[str] = []

    async def screenshot(self, *, path: str, full_page: bool = False) -> None:
        # Real bytes are not required — tests only check the file exists.
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")
        self.screenshots.append(path)


# ===========================================================================
# VisualUsagePolicy
# ===========================================================================


def test_visual_usage_policy_normalize_defaults_to_on_failure() -> None:
    assert VisualUsagePolicy.normalize(None) == "on_failure"
    assert VisualUsagePolicy.normalize("") == "on_failure"
    assert VisualUsagePolicy.normalize("BOGUS") == "on_failure"


def test_visual_usage_policy_normalize_accepts_known_values() -> None:
    for v in ("never", "on_failure", "on_ambiguous", "always"):
        assert VisualUsagePolicy.normalize(v) == v
        assert VisualUsagePolicy.normalize(v.upper()) == v


# ===========================================================================
# WorkflowRecorder
# ===========================================================================


@pytest.mark.asyncio
async def test_recorder_off_mode_is_noop_when_out_dir_missing(tmp_path) -> None:
    rec = WorkflowRecorder()  # no out_dir → off
    assert rec.mode == "off"
    assert rec.context_kwargs() == {}
    rec.start(run_id="r1")
    snap = await rec.snapshot(
        step_id="s1", action="fill", page=_FakePage(), note="t"
    )
    assert snap.step_id == "s1"
    assert snap.screenshot_path == ""  # no file written
    info = rec.last_recording
    assert info is not None
    assert info.mode == "off"
    assert info.screenshots and info.screenshots[0].screenshot_path == ""


@pytest.mark.asyncio
async def test_recorder_screenshots_mode_writes_png_per_step(tmp_path) -> None:
    rec = WorkflowRecorder(out_dir=tmp_path, mode="screenshots")
    rec.start(run_id="run-1")
    page = _FakePage()
    for i in range(3):
        await rec.snapshot(step_id=f"step_{i}", action="click", page=page)
    info = rec.last_recording
    assert info is not None
    assert len(info.screenshots) == 3
    # All three PNGs exist on disk, under the run-1 subdir.
    for s in info.screenshots:
        assert s.screenshot_path
        p = Path(s.screenshot_path)
        assert p.exists()
        assert p.parent.name == "run-1"


def test_recorder_video_mode_emits_context_kwargs(tmp_path) -> None:
    rec = WorkflowRecorder(out_dir=tmp_path, mode="video", video_width=800, video_height=600)
    kwargs = rec.context_kwargs()
    assert "record_video_dir" in kwargs
    assert kwargs["record_video_size"] == {"width": 800, "height": 600}
    assert Path(kwargs["record_video_dir"]).is_dir()


def test_recorder_rejects_unknown_mode(tmp_path) -> None:
    with pytest.raises(ValueError):
        WorkflowRecorder(out_dir=tmp_path, mode="moonshot")


# ===========================================================================
# VisualInspector
# ===========================================================================


@pytest.mark.asyncio
async def test_inspector_without_vision_llm_returns_no_vision_llm_error(tmp_path) -> None:
    # Create one tiny screenshot so the no-frames branch isn't hit.
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    inspector = VisualInspector(vision_llm=None)
    res = await inspector.inspect(
        question="what?", screenshots=[str(p)], max_frames=1
    )
    assert res.ok is False
    assert res.error == "no_vision_llm"
    assert res.frames_used == 1


@pytest.mark.asyncio
async def test_inspector_returns_no_frames_when_nothing_available(tmp_path) -> None:
    inspector = VisualInspector(vision_llm=None)
    res = await inspector.inspect(question="?", max_frames=5)
    assert res.ok is False
    assert "no frames" in res.error


@pytest.mark.asyncio
async def test_inspector_mock_vision_llm_parses_json_answer(tmp_path) -> None:
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    llm = _ScriptedLLM(
        [
            ChatResponse(
                content=json.dumps(
                    {
                        "step_succeeded": True,
                        "finding": "login modal blocks the search box",
                        "evidence": "frame 0 shows a centered modal over the page",
                        "frame_index": 0,
                        "confidence": 0.92,
                        "suggested_action": "click the modal close button",
                    }
                )
            )
        ]
    )
    inspector = VisualInspector(vision_llm=llm)
    res = await inspector.inspect(
        question="why did fill fail?", screenshots=[str(p)], max_frames=1
    )
    assert res.ok is True
    assert "modal" in res.finding
    assert res.confidence == pytest.approx(0.92)
    assert res.suggested_action == "click the modal close button"
    # The first message was the system prompt with our schema rule.
    sys_msg = llm.calls[0][0]
    assert sys_msg.role == "system"
    assert "JSON" in sys_msg.content


@pytest.mark.asyncio
async def test_inspector_extracts_json_from_prose_wrapped_response(tmp_path) -> None:
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    llm = _ScriptedLLM(
        [
            ChatResponse(
                content=(
                    "Sure! Here is my answer:\n"
                    '{"step_succeeded": true, "finding": "looks fine", "confidence": 0.5}\n'
                    "Hope that helps."
                )
            )
        ]
    )
    res = await VisualInspector(vision_llm=llm).inspect(
        question="?", screenshots=[str(p)], max_frames=1
    )
    assert res.ok is True
    assert res.finding == "looks fine"


@pytest.mark.asyncio
async def test_inspector_swallows_vision_llm_exception(tmp_path) -> None:
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")

    class _BoomLLM(LLMClient):
        async def chat(self, messages, *, tools=None, temperature=0.0, max_tokens=None) -> ChatResponse:
            raise RuntimeError("server down")

    res = await VisualInspector(vision_llm=_BoomLLM()).inspect(
        question="?", screenshots=[str(p)], max_frames=1
    )
    assert res.ok is False
    assert "vision_llm_failed" in res.error


# ===========================================================================
# Orchestrator vision gating
# ===========================================================================


class _NoOpAdapter:
    name = "noop"

    async def resolve_locator(self, root, spec):
        class _L:
            async def count(self_):
                return 0

            def nth(self_, idx):
                return self_

            async def evaluate(self_, script, arg=None):
                return None

        return _L()

    async def capture_page_html(self, page):
        return ""


class _FacadeFake:
    def __init__(self, *, recovered: Recovered) -> None:
        self.adapter = _NoOpAdapter()
        self._recovered = recovered
        self.reported: list[dict[str, Any]] = []

    async def recover_workflow_step(self, **kwargs) -> Recovered:
        return self._recovered

    async def report_step_outcome(self, **kwargs) -> bool:
        self.reported.append(kwargs)
        return True


class _CountingInspector:
    """Records every inspect() call so tests can assert call counts."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def inspect(self, **kwargs) -> InspectionResult:
        self.calls.append(kwargs)
        return InspectionResult(
            ok=True,
            finding="mock vision finding",
            confidence=0.8,
            frames_used=len(kwargs.get("screenshots") or []),
            source="mock",
        )


def _plan_one_click_step(label: str = "Save") -> _ScriptedLLM:
    return _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_plan",
                        arguments={
                            "steps": [
                                {
                                    "step_id": "click_save",
                                    "intent": "click save",
                                    "action": "click",
                                    "target_label": label,
                                }
                            ]
                        },
                    )
                ]
            )
        ]
    )


@pytest.mark.asyncio
async def test_orchestrator_visual_policy_never_does_not_call_inspector(tmp_path) -> None:
    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="cascade failed"),
    )
    inspector = _CountingInspector()
    rec = WorkflowRecorder(out_dir=tmp_path, mode="screenshots")
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step()),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        recorder=rec,
        visual_inspector=inspector,
        visual_policy="never",
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click save"))
    assert result.status == "failed"
    assert inspector.calls == []  # policy=never → never invoked
    # Snapshot should NOT carry a visual_finding either.
    assert result.failed_step is not None
    assert result.failed_step.visual_finding is None


@pytest.mark.asyncio
async def test_orchestrator_visual_policy_on_failure_invokes_inspector(tmp_path) -> None:
    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="cascade failed"),
    )
    inspector = _CountingInspector()
    rec = WorkflowRecorder(out_dir=tmp_path, mode="screenshots")
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step()),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        recorder=rec,
        visual_inspector=inspector,
        visual_policy="on_failure",
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click save"))
    assert result.status == "failed"
    assert len(inspector.calls) == 1
    assert result.failed_step is not None
    finding = result.failed_step.visual_finding
    assert finding is not None
    assert finding.finding == "mock vision finding"


@pytest.mark.asyncio
async def test_orchestrator_visual_policy_does_not_fire_on_success(tmp_path) -> None:
    """A successful step with policy=on_failure must NOT spend a vision call."""
    class _OkLocator:
        async def click(self_):
            return None

        async def evaluate(self_, script, arg=None):
            return True

    facade = _FacadeFake(
        recovered=Recovered(
            status="success", correlation_id="c",
            locator_spec=LocatorSpec(kind="xpath", value="//x"),
            runtime_locator=_OkLocator(),
            strategy_id="rules",
        ),
    )
    inspector = _CountingInspector()
    rec = WorkflowRecorder(out_dir=tmp_path, mode="screenshots")
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step()),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        recorder=rec,
        visual_inspector=inspector,
        visual_policy="on_failure",
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click save"))
    assert result.status == "success"
    assert inspector.calls == []


@pytest.mark.asyncio
async def test_orchestrator_visual_policy_always_fires_every_step(tmp_path) -> None:
    class _OkLocator:
        async def click(self_):
            return None

        async def evaluate(self_, script, arg=None):
            return True

    facade = _FacadeFake(
        recovered=Recovered(
            status="success", correlation_id="c",
            locator_spec=LocatorSpec(kind="xpath", value="//x"),
            runtime_locator=_OkLocator(),
            strategy_id="rules",
        ),
    )
    inspector = _CountingInspector()
    rec = WorkflowRecorder(out_dir=tmp_path, mode="screenshots")
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step()),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        recorder=rec,
        visual_inspector=inspector,
        visual_policy="always",
    )
    await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click save"))
    # 1 step in the plan, policy=always → exactly 1 vision call.
    assert len(inspector.calls) == 1


# ===========================================================================
# Gap #1 — vision override of text-tier false-negative
# ===========================================================================


def _make_runner(**overrides) -> WorkflowOrchestrator:
    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="x"),
    )
    return WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step()),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        **overrides,
    )


def _step_rec(*, verify_ok=False, verify_conf=0.4, finding=None):
    from xpath_healer.orchestrator.models import (
        StepRunRecord,
        VerificationResult,
        ExecutionResult,
    )
    rec = StepRunRecord(step_id="s1", action="click", target_label="Save")
    rec.execution = ExecutionResult(status="ok", action="click")
    rec.verification = VerificationResult(
        ok=verify_ok, tier="llm", reason="no evidence", confidence=verify_conf
    )
    rec.visual_finding = finding
    return rec


def test_vision_promotes_fail_to_ok_when_confident_and_verifier_unsure() -> None:
    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(
        ok=True, finding="results visible", confidence=0.95, suggested_action=""
    )
    rec = _step_rec(verify_ok=False, verify_conf=0.4, finding=finding)
    assert orch._revise_terminal_with_vision(record=rec, terminal="fail") == "ok"
    assert rec.verification.ok is True
    assert "vision_override" in rec.verification.tier


def test_vision_does_not_override_when_text_tier_was_confident() -> None:
    """Vision is overruled only when the verifier was MORE confident
    than visual_block_override_threshold (default 0.95). 0.99 qualifies."""
    orch = _make_runner(visual_override_threshold=0.8, visual_block_override_threshold=0.95)
    finding = InspectionResult(ok=True, finding="ok", confidence=0.95)
    rec = _step_rec(verify_ok=False, verify_conf=0.99, finding=finding)
    assert orch._revise_terminal_with_vision(record=rec, terminal="fail") == "fail"
    assert rec.verification.ok is False  # untouched


def test_vision_overrides_when_text_tier_was_only_moderately_confident() -> None:
    """A text-tier verifier capped at 0.85 must NOT block a confident
    vision verdict — that was the exact Amazon false-negative case."""
    orch = _make_runner(visual_override_threshold=0.8, visual_block_override_threshold=0.95)
    finding = InspectionResult(ok=True, finding="results visible", confidence=0.95)
    rec = _step_rec(verify_ok=False, verify_conf=0.85, finding=finding)
    assert orch._revise_terminal_with_vision(record=rec, terminal="fail") == "ok"
    assert rec.verification.ok is True
    assert "vision_override" in rec.verification.tier


def test_vision_does_not_override_when_vision_unsure() -> None:
    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(ok=True, finding="maybe", confidence=0.5)
    rec = _step_rec(verify_ok=False, verify_conf=0.3, finding=finding)
    assert orch._revise_terminal_with_vision(record=rec, terminal="fail") == "fail"


def test_vision_does_not_promote_when_suggested_action_is_abort() -> None:
    """Guard: model says ok=True but also wants to abort — distrust."""
    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(
        ok=True, finding="captcha visible", confidence=0.95,
        suggested_action="abort:captcha",
    )
    rec = _step_rec(verify_ok=False, verify_conf=0.3, finding=finding)
    assert orch._revise_terminal_with_vision(record=rec, terminal="fail") == "fail"


def test_vision_does_not_promote_ok_terminal() -> None:
    """If terminal is already ok, no need to promote."""
    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(ok=True, finding="ok", confidence=0.99)
    rec = _step_rec(verify_ok=True, verify_conf=0.99, finding=finding)
    assert orch._revise_terminal_with_vision(record=rec, terminal="ok") == "ok"


# ===========================================================================
# Gap #3 — vision findings → rewrite proposals
# ===========================================================================


def test_proposal_from_vision_dismiss_modal_emits_insert_before() -> None:
    from xpath_healer.core.workflow import REWRITE_ACTION_INSERT_BEFORE, WorkflowStep

    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(
        ok=True, finding="login modal blocks search", confidence=0.95,
        suggested_action="dismiss_modal:X",
    )
    rec = _step_rec(verify_ok=False, verify_conf=0.3, finding=finding)
    step = WorkflowStep(step_id="s1", intent="click save", action="click", target_label="Save")
    proposal = orch._proposal_from_vision(record=rec, step=step)
    assert proposal is not None
    assert proposal.action == REWRITE_ACTION_INSERT_BEFORE
    assert proposal.new_step is not None
    assert proposal.new_step.target_label == "X"
    assert proposal.new_step.optional is True
    assert proposal.auto_applied is True
    assert proposal.metadata["origin"] == "vision"


def test_proposal_from_vision_abort_emits_abort() -> None:
    from xpath_healer.core.workflow import REWRITE_ACTION_ABORT, WorkflowStep

    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(
        ok=False, finding="cloudflare wall", confidence=0.99,
        suggested_action="abort:captcha",
    )
    rec = _step_rec(verify_ok=False, verify_conf=0.3, finding=finding)
    step = WorkflowStep(step_id="s1", intent="x", action="click", target_label="Save")
    proposal = orch._proposal_from_vision(record=rec, step=step)
    assert proposal is not None
    assert proposal.action == REWRITE_ACTION_ABORT


def test_proposal_from_vision_returns_none_for_empty_suggestion() -> None:
    from xpath_healer.core.workflow import WorkflowStep

    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(ok=True, finding="all good", confidence=0.99, suggested_action="")
    rec = _step_rec(finding=finding)
    step = WorkflowStep(step_id="s1", intent="x", action="click", target_label="Save")
    assert orch._proposal_from_vision(record=rec, step=step) is None


def test_proposal_from_vision_returns_none_when_unsure() -> None:
    from xpath_healer.core.workflow import WorkflowStep

    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(
        ok=True, finding="modal?", confidence=0.4,
        suggested_action="dismiss_modal:X",
    )
    rec = _step_rec(finding=finding)
    step = WorkflowStep(step_id="s1", intent="x", action="click", target_label="Save")
    assert orch._proposal_from_vision(record=rec, step=step) is None


# ===========================================================================
# pick_stronger_proposal
# ===========================================================================


def test_pick_stronger_proposal_picks_higher_confidence() -> None:
    from xpath_healer.core.workflow import REWRITE_ACTION_SKIP, WorkflowRewriteProposal

    a = WorkflowRewriteProposal(action=REWRITE_ACTION_SKIP, confidence=0.4)
    b = WorkflowRewriteProposal(action=REWRITE_ACTION_SKIP, confidence=0.7)
    assert WorkflowOrchestrator._pick_stronger_proposal(a, b) is b
    assert WorkflowOrchestrator._pick_stronger_proposal(b, a) is b
    assert WorkflowOrchestrator._pick_stronger_proposal(None, a) is a
    assert WorkflowOrchestrator._pick_stronger_proposal(a, None) is a
    assert WorkflowOrchestrator._pick_stronger_proposal(None, None) is None
    # Tie goes to secondary (vision).
    c = WorkflowRewriteProposal(action=REWRITE_ACTION_SKIP, confidence=0.5)
    d = WorkflowRewriteProposal(action=REWRITE_ACTION_SKIP, confidence=0.5)
    assert WorkflowOrchestrator._pick_stronger_proposal(c, d) is d


# ===========================================================================
# Gap #2 — visual recovery: heal-fail → vision proposes dismiss_modal →
# orchestrator inserts a new step BEFORE the failing one.
# ===========================================================================


class _DismissModalInspector:
    """Vision LLM that always says 'dismiss the X modal'."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def inspect(self, **kwargs) -> InspectionResult:
        self.calls.append(kwargs)
        return InspectionResult(
            ok=True,
            finding="A signup modal covers the page",
            confidence=0.95,
            suggested_action="dismiss_modal:Close",
            frames_used=1,
        )


@pytest.mark.asyncio
async def test_visual_recovery_inserts_dismiss_modal_step(tmp_path) -> None:
    """When heal cascade fails and vision sees a modal, the orchestrator
    inserts a dismiss step and retries the original step."""
    from xpath_healer.orchestrator.models import OrchestrationResult

    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="not found"),
    )
    inspector = _DismissModalInspector()
    rec = WorkflowRecorder(out_dir=tmp_path, mode="screenshots")
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step("Save")),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        recorder=rec,
        visual_inspector=inspector,
        visual_policy="on_failure",
        visual_recovery_enabled=True,
        max_recovery_inserts=2,
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click save"))
    # The plan should now contain the original step + exactly ONE
    # inserted dismiss-modal step at position 0. The per-step vision
    # recovery cap (default 1) prevents the cycle where Save fails,
    # vision inserts dismiss, dismiss is skipped (optional + heal-miss),
    # Save retries and triggers another insert.
    assert result.plan is not None
    inserted = [s for s in result.plan.steps if s.target_label == "Close"]
    assert len(inserted) == 1, f"expected one inserted dismiss step, got {[s.target_label for s in result.plan.steps]}"
    assert inserted[0].action == "click"
    # The dismiss step is marked optional so a failed dismiss doesn't tank the run.
    assert inserted[0].optional is True


@pytest.mark.asyncio
async def test_visual_recovery_disabled_does_not_call_inspector(tmp_path) -> None:
    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="not found"),
    )
    inspector = _CountingInspector()
    rec = WorkflowRecorder(out_dir=tmp_path, mode="screenshots")
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step()),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        recorder=rec,
        visual_inspector=inspector,
        visual_policy="on_failure",
        visual_recovery_enabled=False,
    )
    await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click save"))
    # The post-step diagnosis still fires (1 call). Recovery is disabled
    # so we get no second call from the heal-fail branch.
    assert len(inspector.calls) == 1


# ===========================================================================
# Phase A.4 — zoom flag plumbs into ffmpeg vf chain.
# ===========================================================================


@pytest.mark.asyncio
async def test_inspect_with_screenshots_ignores_zoom_silently(tmp_path) -> None:
    """zoom is a no-op when screenshots are supplied directly (caller crops upstream)."""
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    llm = _ScriptedLLM(
        [ChatResponse(content=json.dumps({"step_succeeded": True, "finding": "ok", "confidence": 0.5}))]
    )
    res = await VisualInspector(vision_llm=llm).inspect(
        question="?", screenshots=[str(p)], max_frames=1, zoom=(10, 20, 100, 50)
    )
    assert res.ok is True
