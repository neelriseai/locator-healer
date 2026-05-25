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


# ===========================================================================
# "Locator healer eyes" doc — round-2 changes
# ===========================================================================


def test_merge_candidates_deduped_keeps_unique_pairs() -> None:
    """A11y candidate with the same (role, text) as a DOM candidate
    should NOT be appended; a distinct pair should."""
    primary = [
        {"index": 0, "tag": "button", "role": "button", "text": "Sign in", "css_selector": "#login"},
        {"index": 1, "tag": "a", "role": "link", "text": "Help", "css_selector": "a.help"},
    ]
    secondary = [
        # Duplicate (role=button + text=Sign in) → dropped.
        {"index": 0, "tag": "button", "role": "button", "text": "Sign in", "css_selector": 'role=button[name="Sign in"]'},
        # Distinct (role=textbox + text=Username) → kept.
        {"index": 1, "tag": "textbox", "role": "textbox", "text": "Username", "css_selector": 'role=textbox[name="Username"]'},
        # Empty text → skipped.
        {"index": 2, "tag": "button", "role": "button", "text": "", "css_selector": "x"},
    ]
    merged = WorkflowOrchestrator._merge_candidates_deduped(primary, secondary)
    selectors = [c["css_selector"] for c in merged]
    assert "#login" in selectors
    assert 'role=textbox[name="Username"]' in selectors
    assert 'role=button[name="Sign in"]' not in selectors  # de-duped
    # Indices are re-numbered.
    for i, c in enumerate(merged):
        assert c["index"] == i


@pytest.mark.asyncio
async def test_extract_a11y_candidates_walks_tree(tmp_path) -> None:
    """A fake page with a Playwright-shaped a11y tree should yield
    actionable candidates with role= selectors."""

    class _A11y:
        async def snapshot(self_):
            return {
                "role": "WebArea",
                "name": "Login",
                "children": [
                    {"role": "textbox", "name": "Username", "children": []},
                    {"role": "textbox", "name": "Password", "disabled": False, "children": []},
                    {"role": "button", "name": "Sign in", "children": []},
                    # Generic landmark should be skipped.
                    {"role": "region", "name": "Footer", "children": [
                        {"role": "link", "name": "Forgot password", "children": []},
                    ]},
                ],
            }

    class _Page:
        accessibility = _A11y()

    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="x"),
    )
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step()),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    out = await orch._extract_a11y_candidates(_Page())
    texts_by_role: dict[str, list[str]] = {}
    for c in out:
        texts_by_role.setdefault(c["role"], []).append(c["text"])
    selectors = [c["css_selector"] for c in out]
    # Both textboxes are kept.
    assert "textbox" in texts_by_role
    assert {"Username", "Password"} <= set(texts_by_role["textbox"])
    # Button candidate carries a Playwright role= selector.
    assert 'role=button[name="Sign in"]' in selectors
    # Link inside region IS kept (region is just a parent we walk through).
    assert "link" in texts_by_role
    # Region (landmark role) itself should NOT be emitted as a candidate.
    assert "region" not in texts_by_role


@pytest.mark.asyncio
async def test_extract_a11y_candidates_no_accessibility_api_returns_empty() -> None:
    """Adapters without a Playwright .accessibility attribute must
    degrade silently (returns [], does not raise)."""
    class _NoA11yPage:
        pass

    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="x"),
    )
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step()),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    assert await orch._extract_a11y_candidates(_NoA11yPage()) == []


@pytest.mark.asyncio
async def test_page_state_observer_normalises_evaluate_failure() -> None:
    """If the page raises during evaluate, observe() returns {} rather
    than propagating."""
    from xpath_healer.orchestrator import PageStateObserver

    class _BoomPage:
        async def evaluate(self_, script):
            raise RuntimeError("page detached")

    observer = PageStateObserver()
    assert await observer.observe(_BoomPage()) == {}


@pytest.mark.asyncio
async def test_page_state_observer_returns_evaluate_output() -> None:
    """Happy path: the JS returns a dict; observe() forwards it."""
    from xpath_healer.orchestrator import PageStateObserver

    class _Page:
        async def evaluate(self_, script):
            return {
                "url": "https://x.test/login",
                "title": "Login",
                "page_type": "auth",
                "forms": [{"name": "f", "fields": [], "actions": []}],
                "buttons": [{"text": "Sign in", "disabled": False, "bbox": {"x": 0, "y": 0, "w": 80, "h": 30}}],
                "errors": [],
                "modals": [],
                "tables_count": 0,
                "first_table_columns": [],
                "next_possible_actions": ["click_sign_in"],
            }

    observer = PageStateObserver()
    state = await observer.observe(_Page())
    assert state["page_type"] == "auth"
    summary = observer.short_summary(state)
    assert "page_type=auth" in summary
    assert "Sign in" in summary
    assert "NEXT_ACTIONS" in summary


# ===========================================================================
# #6 Budget-exhaustion stress tests
# ===========================================================================


def _plan_two_step_with_optional_dismiss(label_main: str = "Save") -> _ScriptedLLM:
    """Plan: optional dismiss-modal (will heal-miss) + required main step.

    Used to drive the optional-skip + budget paths."""
    return _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1", name="commit_plan",
                        arguments={
                            "steps": [
                                {
                                    "step_id": "dismiss_modal",
                                    "intent": "dismiss optional modal",
                                    "action": "click",
                                    "target_label": "Close",
                                    "optional": True,
                                },
                                {
                                    "step_id": "do_main",
                                    "intent": "main task",
                                    "action": "click",
                                    "target_label": label_main,
                                },
                            ]
                        },
                    )
                ]
            )
        ]
    )


@pytest.mark.asyncio
async def test_max_recovery_inserts_zero_blocks_vision_inserts(tmp_path) -> None:
    """With max_recovery_inserts=0, a vision-derived dismiss-modal
    proposal must NOT splice a new step into the plan."""
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
        max_recovery_inserts=0,
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click save"))
    # Insert was proposed but the budget is 0 → orchestrator returns
    # failed instead of mutating the plan.
    assert result.status == "failed"
    # Plan must contain exactly the original step, no inserts.
    assert result.plan is not None
    assert [s.target_label for s in result.plan.steps] == ["Save"]


@pytest.mark.asyncio
async def test_max_replans_zero_skips_replan_after_url_change(tmp_path) -> None:
    """With max_replans=0, _page_changed_significantly fires but the
    orchestrator does NOT re-decompose."""
    class _OkLocator:
        async def click(self_):
            return None
        async def scroll_into_view_if_needed(self_, timeout=0):
            return None
        async def evaluate(self_, script, arg=None):
            return True

    class _NavigatingPage:
        """URL changes between successive _current_url calls."""
        def __init__(self_):
            self_._urls = [
                "",                          # initial (no start_url)
                "https://x.test/before",     # after first step succeeds
                "https://x.test/after",      # after second step — DIFFERENT path
            ]
            self_._idx = 0

        @property
        def url(self_):
            i = min(self_._idx, len(self_._urls) - 1)
            self_._idx += 1
            return self_._urls[i]

        async def screenshot(self_, *, path, full_page=False):
            from pathlib import Path
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")

    facade = _FacadeFake(
        recovered=Recovered(
            status="success", correlation_id="c",
            locator_spec=LocatorSpec(kind="xpath", value="//x"),
            runtime_locator=_OkLocator(),
            strategy_id="rules",
        ),
    )
    decomposer_calls: list[int] = []
    class _CountingDecomposer:
        async def decompose(self_, *, goal, adapter, page):
            decomposer_calls.append(1)
            return await AgenticGoalDecomposer(_plan_two_step_with_optional_dismiss()).decompose(
                goal=goal, adapter=adapter, page=page
            )

    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=_CountingDecomposer(),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        max_replans=0,
        replan_on_url_change=True,
    )
    await orch.run(page=_NavigatingPage(), goal=WorkflowGoal(text="navigate twice"))
    # max_replans=0 → decomposer called exactly once (the initial plan),
    # never a second time even though the URL path changed.
    assert len(decomposer_calls) == 1


@pytest.mark.asyncio
async def test_vision_insert_cap_holds_across_consecutive_failures(tmp_path) -> None:
    """The per-step vision-insert cap (1) must hold even when the same
    step fails repeatedly. Without the cap, we'd see N inserts."""
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
        # Plenty of budget; cap must come from per-step counter, not budget.
        max_recovery_inserts=10,
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click save"))
    assert result.plan is not None
    # Plan ends up with: 1 inserted dismiss + original Save = 2 steps total.
    # The per-step cap of 1 prevents an unbounded cascade.
    inserts = [s for s in result.plan.steps if s.target_label == "Close"]
    assert len(inserts) == 1, (
        f"per-step vision-insert cap broken; got "
        f"{[s.target_label for s in result.plan.steps]}"
    )


# ===========================================================================
# #3 Overlay-detection: _click recovers via JS-click when native fails
# ===========================================================================


@pytest.mark.asyncio
async def test_click_recovers_via_js_when_native_throws_intercepted() -> None:
    """A locator whose native click throws (overlay intercepted) must
    fall back to JS-click via elementFromPoint detection. The detail
    string must reflect the overlay was detected."""
    from xpath_healer.orchestrator.executor import PlaywrightActionExecutor
    from xpath_healer.orchestrator.models import ACTION_CLICK
    from xpath_healer.core.workflow import WorkflowStep

    class _OverlayedLocator:
        def __init__(self_):
            self_.native_click_attempts = 0
            self_.scroll_in_calls = 0
            self_.evaluate_calls: list[str] = []
            self_.js_click_dispatched = False

        async def scroll_into_view_if_needed(self_, timeout=0):
            self_.scroll_in_calls += 1

        async def click(self_):
            self_.native_click_attempts += 1
            # Simulate Playwright's ElementClickIntercepted.
            raise Exception("locator click intercepted by overlay")

        async def evaluate(self_, script, arg=None):
            self_.evaluate_calls.append(script)
            if "elementFromPoint" in script:
                # Pretend an overlay div is on top.
                return {
                    "intercepted": True,
                    "top_tag": "div",
                    "top_class": "modal-backdrop",
                }
            if "el.click()" in script:
                self_.js_click_dispatched = True
                return True
            return None

    loc = _OverlayedLocator()
    executor = PlaywrightActionExecutor()
    step = WorkflowStep(step_id="s", intent="i", action="click", target_label="Buy")
    result = await executor.execute(
        step=step, locator=loc, page=_FakePage(), value="", adapter=None,
    )
    assert result.status == "ok"
    assert result.action == ACTION_CLICK
    assert loc.scroll_in_calls == 1
    assert loc.native_click_attempts == 1
    assert loc.js_click_dispatched is True
    # The detail string must mention what intercepted the click.
    assert "intercepted" in result.detail.lower()
    assert "modal-backdrop" in result.detail
    # The page_signal should record the JS fallback path.
    assert result.page_signal.get("click_path") == "js_fallback"


@pytest.mark.asyncio
async def test_click_uses_scroll_into_view_before_native_click() -> None:
    """Scroll-into-view must fire BEFORE the native click attempt, so
    below-fold elements are reached without an explicit scroll step."""
    from xpath_healer.orchestrator.executor import PlaywrightActionExecutor
    from xpath_healer.core.workflow import WorkflowStep

    call_order: list[str] = []

    class _NormalLocator:
        async def scroll_into_view_if_needed(self_, timeout=0):
            call_order.append("scroll")
        async def click(self_):
            call_order.append("native_click")
        async def evaluate(self_, script, arg=None):
            return None

    loc = _NormalLocator()
    executor = PlaywrightActionExecutor()
    step = WorkflowStep(step_id="s", intent="i", action="click", target_label="OK")
    result = await executor.execute(
        step=step, locator=loc, page=_FakePage(), value="", adapter=None,
    )
    assert result.status == "ok"
    assert call_order == ["scroll", "native_click"]


# ===========================================================================
# #1 Force-exercise visual candidate heal (cascade disabled)
# ===========================================================================


@pytest.mark.asyncio
async def test_candidate_heal_drives_execution_when_cascade_fails(tmp_path) -> None:
    """Disable the heal cascade entirely (facade returns failed always).
    Vision returns a CandidatePick with a stable selector. The orchestrator
    must use page.locator(selector) to execute the action."""
    from xpath_healer.orchestrator.visual import CandidatePick

    page_locator_calls: list[str] = []
    click_calls: list[str] = []

    class _FakeBuyLocator:
        async def scroll_into_view_if_needed(self_, timeout=0):
            return None
        async def click(self_):
            click_calls.append("clicked")
        async def evaluate(self_, script, arg=None):
            return True

    class _LocatorWithFirst:
        """Playwright-shaped fake: `page.locator(sel).first` returns a
        locator. We model that with `first` returning the same fake."""
        def __init__(self_):
            self_._inner = _FakeBuyLocator()
        @property
        def first(self_):
            return self_._inner
        # If the runner ever skips .first and uses methods directly,
        # delegate them so the test still works.
        async def click(self_):
            return await self_._inner.click()
        async def scroll_into_view_if_needed(self_, timeout=0):
            return await self_._inner.scroll_into_view_if_needed(timeout=timeout)
        async def evaluate(self_, script, arg=None):
            return await self_._inner.evaluate(script, arg)

    class _PageWithLocator:
        url = "https://x.test/"
        async def screenshot(self_, *, path, full_page=False):
            from pathlib import Path
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")
        async def evaluate(self_, script, arg=None):
            # Return one DOM candidate.
            if "MIN_REPEATS" in script:
                return []
            if "candidateId" in script or "MAX" in script:
                return [{
                    "index": 0, "tag": "button", "text": "Buy now",
                    "role": "button", "aria_label": "",
                    "placeholder": "", "href": "", "type": "",
                    "css_selector": "#buy-btn",
                    "bbox": [10, 20, 80, 30], "visible": True, "enabled": True,
                }]
            return None
        def locator(self_, selector):
            page_locator_calls.append(selector)
            return _LocatorWithFirst()
        # No accessibility API → a11y candidates degrade to [].

    class _VisionPicksBuy:
        async def inspect(self_, **kwargs):
            return InspectionResult(ok=True, finding="ok", confidence=0.99)
        async def pick_candidate(self_, *, intent, candidates, screenshot_path):
            return CandidatePick(
                index=0, css_selector="#buy-btn",
                reason="matches buy intent",
                confidence=0.95,
                candidate={"tag": "button", "text": "Buy now"},
            )

    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="cascade off"),
    )
    rec = WorkflowRecorder(out_dir=tmp_path, mode="screenshots")
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(_plan_one_click_step("Buy now")),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        recorder=rec,
        visual_inspector=_VisionPicksBuy(),
        visual_policy="on_failure",
    )
    result = await orch.run(page=_PageWithLocator(), goal=WorkflowGoal(text="buy"))
    # Vision picked #buy-btn → orchestrator called page.locator('#buy-btn').
    assert "#buy-btn" in page_locator_calls
    # The locator's click was actually invoked (executor used the picked locator).
    assert click_calls == ["clicked"]
    # The step record reflects which strategy healed it.
    assert any(
        r.heal_strategy == "visual_candidate_pick" for r in result.completed_steps
    ), f"expected visual_candidate_pick strategy on a step; got {[r.heal_strategy for r in result.completed_steps]}"


# ===========================================================================
# #2 Force-exercise PageStateObserver in decomposer prompt
# ===========================================================================


@pytest.mark.asyncio
async def test_decomposer_prompt_includes_page_state_when_present(monkeypatch) -> None:
    """When PageStateObserver returns a non-empty state, the user
    message sent to the LLM MUST include a `page_state` key with the
    forms/buttons/modals carved out. Without page_state, the prompt
    falls back to outline-only."""
    captured_prompts: list[str] = []

    class _CapturingLLM(LLMClient):
        async def chat(self_, messages, *, tools=None, temperature=0.0, max_tokens=None):
            # The second message is the user payload.
            user_text = messages[-1].content
            captured_prompts.append(user_text if isinstance(user_text, str) else json.dumps(user_text))
            return ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c", name="commit_plan",
                        arguments={
                            "steps": [
                                {"step_id": "s", "intent": "x", "action": "click", "target_label": "OK"}
                            ]
                        },
                    )
                ]
            )

    class _PageReturningState:
        async def evaluate(self_, script):
            # _OBSERVE_JS in page_state.py is matched by 'page_type' marker.
            if "next_possible_actions" in script:
                return {
                    "url": "https://x.test/login",
                    "title": "Login",
                    "viewport": {"w": 1280, "h": 800, "scroll_x": 0, "scroll_y": 0, "dpr": 1},
                    "page_type": "auth",
                    "forms": [{
                        "name": "loginForm",
                        "fields": [{"label": "Username", "type": "text", "required": True, "filled": False, "placeholder": ""}],
                        "actions": ["Sign in"],
                    }],
                    "buttons": [{"text": "Sign in", "disabled": False, "bbox": {"x": 0, "y": 0, "w": 80, "h": 30}}],
                    "links": [],
                    "errors": [],
                    "modals": [],
                    "tables_count": 0,
                    "first_table_columns": [],
                    "next_possible_actions": ["fill_username", "click_sign_in"],
                }
            # Outline read: return a tiny payload so retry-outline doesn't fire.
            return None
        async def wait_for_load_state(self_, *a, **kw):
            return None

    # Patch _exec_read_outline so the decomposer's outline read returns text.
    from xpath_healer.mcp import explorer as exp_mod

    async def fake_outline(adapter, page, *, max_chars=8000, focus_text=""):
        return {"outline": "input[type=text,placeholder=Username] \"Username\"\nbutton \"Sign in\"\n" * 30}

    monkeypatch.setattr(exp_mod, "_exec_read_outline", fake_outline)
    # The decomposer imports it directly, so patch THAT binding too.
    from xpath_healer.orchestrator import decomposer as dcm_mod
    monkeypatch.setattr(dcm_mod, "_exec_read_outline", fake_outline)

    llm = _CapturingLLM()
    decomposer = AgenticGoalDecomposer(llm)
    await decomposer.decompose(
        goal=WorkflowGoal(text="log in"),
        adapter=_NoOpAdapter(),
        page=_PageReturningState(),
    )
    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    # The prompt MUST contain the page_state block.
    assert "page_state" in prompt
    assert "page_type" in prompt
    assert "auth" in prompt
    # And the next_possible_actions hint is forwarded.
    assert "click_sign_in" in prompt or "fill_username" in prompt


# ===========================================================================
# Demote direction of vision override (vision says no, text-tier said yes)
# ===========================================================================


# ===========================================================================
# #4 Telemetry harness
# ===========================================================================


@pytest.mark.asyncio
async def test_telemetry_counts_llm_calls_tokens_and_heal_strategies(tmp_path) -> None:
    """Telemetry must record per-run metrics: LLM call count, token
    totals (when usage is reported), heal-strategy distribution, and
    total wall time."""
    from xpath_healer.orchestrator import (
        TelemetryCounter,
        TelemetryLLMClient,
    )

    class _CountingLLM(LLMClient):
        async def chat(self_, messages, *, tools=None, temperature=0.0, max_tokens=None):
            return ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c", name="commit_plan",
                        arguments={
                            "steps": [
                                {"step_id": "click_save", "intent": "x", "action": "click", "target_label": "Save"}
                            ]
                        },
                    )
                ],
                metadata={"usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}},
            )

    counter = TelemetryCounter()
    tele_llm = TelemetryLLMClient(_CountingLLM(), counter)

    class _OkLocator:
        async def scroll_into_view_if_needed(self_, timeout=0):
            return None
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
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(tele_llm),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        telemetry=counter,
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click save"))
    assert result.status == "success"
    tele = result.metadata.get("telemetry")
    assert tele is not None
    # 1 decomposer LLM call.
    assert tele["llm_calls"] == 1
    assert tele["llm_total_tokens"] == 150
    assert tele["llm_prompt_tokens"] == 120
    assert tele["llm_completion_tokens"] == 30
    # The heal strategy from the fake facade was "rules".
    assert tele["heal_strategy_counts"].get("rules") == 1
    # We ran exactly one step, so its duration is recorded.
    assert "click_save" in tele["step_durations_ms"]
    # Total run time > 0.
    assert tele["total_seconds"] > 0


@pytest.mark.asyncio
async def test_telemetry_counts_vision_calls_via_wrapper(tmp_path) -> None:
    """TelemetryVisualInspector counts every inspect() AND pick_candidate()
    call against the same counter that tracks LLM calls."""
    from xpath_healer.orchestrator import (
        CandidatePick,
        TelemetryCounter,
        TelemetryVisualInspector,
    )

    class _Inner:
        async def inspect(self_, **kwargs):
            return InspectionResult(ok=True, finding="x", confidence=0.9)
        async def pick_candidate(self_, **kwargs):
            return CandidatePick(index=-1, error="no_match")

    counter = TelemetryCounter()
    wrapper = TelemetryVisualInspector(_Inner(), counter)
    await wrapper.inspect(question="?", screenshots=[], max_frames=1)
    await wrapper.pick_candidate(intent="x", candidates=[], screenshot_path="")
    assert counter.vision_calls == 2
    assert counter.vision_seconds >= 0


@pytest.mark.asyncio
async def test_telemetry_stamped_on_failed_runs_too(tmp_path) -> None:
    """A failed run must still carry telemetry — that's the run where
    we MOST need to know cost (we burned tokens on a failure)."""
    from xpath_healer.orchestrator import TelemetryCounter, TelemetryLLMClient

    class _LLMNoSteps(LLMClient):
        async def chat(self_, messages, *, tools=None, temperature=0.0, max_tokens=None):
            return ChatResponse(
                content="(no tool call)",
                metadata={"usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55}},
            )

    counter = TelemetryCounter()
    tele_llm = TelemetryLLMClient(_LLMNoSteps(), counter)
    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="x"),
    )
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(tele_llm, max_attempts=1),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        telemetry=counter,
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="x"))
    assert result.status == "failed"
    tele = result.metadata.get("telemetry")
    assert tele is not None
    # The decomposer's failed-attempt LLM call is still counted.
    assert tele["llm_calls"] == 1
    assert tele["llm_total_tokens"] == 55


# ===========================================================================
# P3a — OpenAI 429 retry with backoff
# ===========================================================================


@pytest.mark.asyncio
async def test_openai_chat_retries_on_rate_limit_then_succeeds(monkeypatch) -> None:
    """Mock the OpenAI client to raise RateLimitError twice then return
    a real response. The wrapper MUST retry both errors transparently
    and return the eventual success."""
    from xpath_healer.llm import openai_chat as oc_mod

    # Mock RateLimitError so we don't depend on openai's exception
    # hierarchy quirks during testing.
    class _FakeRateLimitError(Exception):
        def __init__(self_, msg):
            super().__init__(msg)
            self_.message = msg

    monkeypatch.setattr(oc_mod, "RateLimitError", _FakeRateLimitError)

    calls = {"n": 0}

    class _FakeCreate:
        async def __call__(self_, **kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise _FakeRateLimitError("Rate limit reached. Please try again in 100ms.")
            # Real-looking response on the third try.
            class _Msg:
                content = "ok"
                tool_calls = None
            class _Choice:
                message = _Msg()
            class _Resp:
                choices = [_Choice()]
                model = "gpt-4o-mini"
                usage = None
            return _Resp()

    class _FakeCompletions:
        create = _FakeCreate()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    # Avoid the AsyncOpenAI import path entirely.
    monkeypatch.setattr(oc_mod, "AsyncOpenAI", lambda **k: _FakeClient())
    monkeypatch.setattr(oc_mod, "AsyncAzureOpenAI", None)

    from xpath_healer.llm.openai_chat import OpenAIChatClient
    client = OpenAIChatClient(
        api_key="test", model="gpt-4o-mini",
        max_retries=5, base_retry_delay=0.01, max_retry_delay=0.05,
    )
    response = await client.chat([ChatMessage(role="user", content="hi")])
    assert response.content == "ok"
    assert calls["n"] == 3  # 2 rate-limits + 1 success


@pytest.mark.asyncio
async def test_openai_chat_gives_up_after_max_retries(monkeypatch) -> None:
    """If the rate limit never clears, the wrapper must give up after
    max_retries and re-raise so the caller sees the failure."""
    from xpath_healer.llm import openai_chat as oc_mod

    class _FakeRateLimitError(Exception):
        def __init__(self_, msg):
            super().__init__(msg)
            self_.message = msg

    monkeypatch.setattr(oc_mod, "RateLimitError", _FakeRateLimitError)

    class _AlwaysRateLimited:
        async def __call__(self_, **kwargs):
            raise _FakeRateLimitError("try again in 10ms")

    class _C:
        chat = type("X", (), {"completions": type("Y", (), {"create": _AlwaysRateLimited()})()})

    monkeypatch.setattr(oc_mod, "AsyncOpenAI", lambda **k: _C())
    monkeypatch.setattr(oc_mod, "AsyncAzureOpenAI", None)
    from xpath_healer.llm.openai_chat import OpenAIChatClient
    client = OpenAIChatClient(
        api_key="t", model="gpt-4o-mini",
        max_retries=2, base_retry_delay=0.01, max_retry_delay=0.02,
    )
    with pytest.raises(_FakeRateLimitError):
        await client.chat([ChatMessage(role="user", content="hi")])


# ===========================================================================
# P3b — replan-on-URL-change focused unit test
# ===========================================================================


@pytest.mark.asyncio
async def test_replan_fires_when_url_path_changes_with_budget(tmp_path) -> None:
    """When the URL path changes between steps AND max_replans > 0, the
    decomposer MUST be called a second time to re-plan the remaining
    work for the new page."""
    class _OkLocator:
        async def click(self_):
            return None
        async def scroll_into_view_if_needed(self_, timeout=0):
            return None
        async def evaluate(self_, script, arg=None):
            return True

    class _PageThatNavigates:
        def __init__(self_):
            # Initial /a (baseline) -> after step 1, URL flipped to /b
            # (DIFFERENT path) -> replan should fire because plan still
            # has step 2 ('stale_step') queued on the old page.
            self_._idx = 0
            self_._urls = [
                "https://x.test/a",   # initial (baseline)
                "https://x.test/b",   # after step 1 — path changed, replan!
                "https://x.test/b",   # after step 2 (the replanned step)
            ]
        @property
        def url(self_):
            i = min(self_._idx, len(self_._urls) - 1)
            self_._idx += 1
            return self_._urls[i]
        async def goto(self_, url, **kw):
            return None
        async def screenshot(self_, *, path, full_page=False):
            from pathlib import Path
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")

    facade = _FacadeFake(
        recovered=Recovered(
            status="success", correlation_id="c",
            locator_spec=LocatorSpec(kind="xpath", value="//x"),
            runtime_locator=_OkLocator(),
            strategy_id="rules",
        ),
    )

    decomposer_calls: list[str] = []

    class _Decomposer:
        async def decompose(self_, *, goal, adapter, page):
            decomposer_calls.append(f"call[{len(decomposer_calls)}]")
            # First call: 2 steps. Replan call: 1 step.
            replanning = bool((goal.constraints or {}).get("replanning"))
            steps_payload = (
                [{"step_id": "after_replan", "intent": "x", "action": "click", "target_label": "Done"}]
                if replanning else
                [
                    {"step_id": "first_step", "intent": "x", "action": "click", "target_label": "Open"},
                    {"step_id": "second_step", "intent": "x", "action": "click", "target_label": "Stale"},
                ]
            )
            return await AgenticGoalDecomposer(_ScriptedLLM([
                ChatResponse(tool_calls=[
                    ToolCall(id="c", name="commit_plan", arguments={"steps": steps_payload}),
                ])
            ])).decompose(goal=goal, adapter=adapter, page=page)

    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=_Decomposer(),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        max_replans=2,
        replan_on_url_change=True,
    )
    result = await orch.run(
        page=_PageThatNavigates(),
        goal=WorkflowGoal(text="navigate", start_url="https://x.test/a"),
    )
    # Two decompose calls: initial plan + one replan after URL changed.
    assert len(decomposer_calls) == 2
    # Final plan must end with the replan-substituted step, not the stale one.
    plan_ids = [s.step_id for s in result.plan.steps]
    assert "after_replan" in plan_ids


@pytest.mark.asyncio
async def test_no_replan_when_url_query_only_changed(tmp_path) -> None:
    """Same path with different query string is NOT a significant page
    change. Decomposer must be called exactly once."""
    class _OkLocator:
        async def click(self_):
            return None
        async def scroll_into_view_if_needed(self_, timeout=0):
            return None
        async def evaluate(self_, script, arg=None):
            return True

    class _PageQueryOnlyChange:
        def __init__(self_):
            self_._idx = 0
            self_._urls = ["https://x.test/a", "https://x.test/a?p=1", "https://x.test/a?p=2"]
        @property
        def url(self_):
            i = min(self_._idx, len(self_._urls) - 1)
            self_._idx += 1
            return self_._urls[i]
        async def goto(self_, url, **kw):
            return None

    facade = _FacadeFake(
        recovered=Recovered(
            status="success", correlation_id="c",
            locator_spec=LocatorSpec(kind="xpath", value="//x"),
            runtime_locator=_OkLocator(),
            strategy_id="rules",
        ),
    )
    decomposer_calls: list[str] = []
    class _Decomposer:
        async def decompose(self_, *, goal, adapter, page):
            decomposer_calls.append("x")
            return await AgenticGoalDecomposer(_ScriptedLLM([
                ChatResponse(tool_calls=[
                    ToolCall(id="c", name="commit_plan", arguments={"steps": [
                        {"step_id": "s1", "intent": "x", "action": "click", "target_label": "A"},
                        {"step_id": "s2", "intent": "x", "action": "click", "target_label": "B"},
                    ]}),
                ])
            ])).decompose(goal=goal, adapter=adapter, page=page)

    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=_Decomposer(),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        max_replans=2,
        replan_on_url_change=True,
    )
    await orch.run(
        page=_PageQueryOnlyChange(),
        goal=WorkflowGoal(text="x", start_url="https://x.test/a"),
    )
    assert len(decomposer_calls) == 1  # no replan for query-only change


# ===========================================================================
# P4 — SLO benchmark harness
# ===========================================================================


def test_slo_check_passes_when_all_targets_met() -> None:
    from xpath_healer.orchestrator import SLO

    slo = SLO(max_total_seconds=10.0, max_llm_calls=5, max_llm_tokens=10_000, max_vision_calls=3, max_step_ms=5_000)
    report = slo.check({
        "total_seconds": 4.2,
        "llm_calls": 3,
        "llm_total_tokens": 2_500,
        "vision_calls": 1,
        "step_durations_ms": {"s1": 1200, "s2": 800},
    })
    assert report["ok"] is True
    for name, c in report["checks"].items():
        assert c["ok"] is True, f"{name} should pass"


def test_slo_check_fails_when_token_budget_exceeded() -> None:
    from xpath_healer.orchestrator import SLO

    slo = SLO(max_llm_tokens=5_000)
    report = slo.check({"llm_total_tokens": 12_000, "total_seconds": 1, "llm_calls": 1, "vision_calls": 0, "step_durations_ms": {}})
    assert report["ok"] is False
    assert report["checks"]["llm_total_tokens"]["ok"] is False
    assert report["checks"]["llm_total_tokens"]["observed"] == 12_000


def test_slo_check_flags_slow_steps() -> None:
    """Any individual step exceeding max_step_ms must surface in the
    report so we can identify which step is the bottleneck."""
    from xpath_healer.orchestrator import SLO

    slo = SLO(max_step_ms=2_000)
    report = slo.check({
        "total_seconds": 5, "llm_calls": 1, "llm_total_tokens": 100, "vision_calls": 0,
        "step_durations_ms": {"fast": 800, "slow_extract": 5_500, "ok_step": 1_200},
    })
    assert report["ok"] is False
    slow = report["checks"]["max_step_ms"]["slow_steps"]
    assert "slow_extract" in slow
    assert slow["slow_extract"] == 5_500
    assert "fast" not in slow


def test_slo_check_returns_safely_on_empty_telemetry() -> None:
    from xpath_healer.orchestrator import SLO

    report = SLO().check({})
    assert report["ok"] is False
    assert "error" in report


# ===========================================================================
# Robustness: concurrent + long-workflow + adversarial-input
# ===========================================================================


@pytest.mark.asyncio
async def test_two_orchestrators_with_separate_counters_run_concurrently_without_leaking_state() -> None:
    """Spec: each WorkflowOrchestrator owns its own TelemetryCounter,
    and two simultaneous run()s must not see each other's tokens /
    heal-strategy / step-duration data. (Same orchestrator + counter
    across two concurrent runs is documented as unsafe — caller is
    expected to instantiate per-run.)"""
    from xpath_healer.orchestrator import (
        TelemetryCounter, TelemetryLLMClient,
    )

    class _CountingLLM(LLMClient):
        def __init__(self_, tag: str) -> None:
            self_.tag = tag
        async def chat(self_, messages, *, tools=None, temperature=0.0, max_tokens=None):
            return ChatResponse(
                tool_calls=[
                    ToolCall(
                        id=f"c-{self_.tag}", name="commit_plan",
                        arguments={
                            "steps": [
                                {"step_id": f"only_step_{self_.tag}", "intent": "x", "action": "click", "target_label": "Save"}
                            ]
                        },
                    )
                ],
                metadata={"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            )

    class _OkLocator:
        async def click(self_):
            return None
        async def scroll_into_view_if_needed(self_, timeout=0):
            return None
        async def evaluate(self_, script, arg=None):
            return True

    def _make_orch(tag: str):
        facade = _FacadeFake(
            recovered=Recovered(
                status="success", correlation_id=tag,
                locator_spec=LocatorSpec(kind="xpath", value="//x"),
                runtime_locator=_OkLocator(),
                strategy_id=f"strategy_{tag}",
            ),
        )
        counter = TelemetryCounter()
        wrapped_llm = TelemetryLLMClient(_CountingLLM(tag), counter)
        orch = WorkflowOrchestrator(
            facade=facade,
            decomposer=AgenticGoalDecomposer(wrapped_llm),
            executor=PlaywrightActionExecutor(),
            verifier=TieredOutcomeVerifier(llm_verifier=None),
            telemetry=counter,
        )
        return orch, counter

    orch_a, counter_a = _make_orch("A")
    orch_b, counter_b = _make_orch("B")

    # Drive both runs concurrently.
    results = await asyncio.gather(
        orch_a.run(page=_FakePage(), goal=WorkflowGoal(text="run A")),
        orch_b.run(page=_FakePage(), goal=WorkflowGoal(text="run B")),
    )
    assert all(r.status == "success" for r in results)

    # Each counter must reflect exactly ONE LLM call (its own decomposer)
    # and ONE strategy (its own facade's). No bleeding.
    assert counter_a.llm_calls == 1
    assert counter_b.llm_calls == 1
    assert counter_a.heal_strategy_counts == {"strategy_A": 1}
    assert counter_b.heal_strategy_counts == {"strategy_B": 1}
    # The two counters are physically distinct objects.
    assert counter_a is not counter_b
    # Step-duration keys are namespaced by step_id so they don't collide.
    assert set(counter_a.step_durations_ms.keys()) == {"only_step_A"}
    assert set(counter_b.step_durations_ms.keys()) == {"only_step_B"}


@pytest.mark.asyncio
async def test_orchestrator_run_resets_telemetry_between_sequential_calls() -> None:
    """Same orchestrator + counter across two sequential run() calls
    must reset between runs — each run's telemetry reflects only its
    own work. This is the contract the drill demos depend on."""
    from xpath_healer.orchestrator import TelemetryCounter, TelemetryLLMClient

    class _Plan(LLMClient):
        async def chat(self_, messages, *, tools=None, temperature=0.0, max_tokens=None):
            return ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c", name="commit_plan",
                        arguments={
                            "steps": [
                                {"step_id": "step_x", "intent": "x", "action": "click", "target_label": "X"}
                            ]
                        },
                    )
                ],
                metadata={"usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}},
            )

    class _OkLocator:
        async def click(self_): return None
        async def scroll_into_view_if_needed(self_, timeout=0): return None
        async def evaluate(self_, script, arg=None): return True

    counter = TelemetryCounter()
    facade = _FacadeFake(
        recovered=Recovered(
            status="success", correlation_id="c",
            locator_spec=LocatorSpec(kind="xpath", value="//x"),
            runtime_locator=_OkLocator(),
            strategy_id="rules",
        ),
    )
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(TelemetryLLMClient(_Plan(), counter)),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        telemetry=counter,
    )
    # Run #1.
    r1 = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="first"))
    t1 = (r1.metadata or {}).get("telemetry") or {}
    assert t1["llm_calls"] == 1
    assert t1["llm_total_tokens"] == 60
    # Run #2 — counter MUST be reset, not cumulative.
    r2 = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="second"))
    t2 = (r2.metadata or {}).get("telemetry") or {}
    assert t2["llm_calls"] == 1, "telemetry must reset between runs"
    assert t2["llm_total_tokens"] == 60


# ---------------------------------------------------------------------------
# Long workflow stress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_handles_50_step_plan_without_blowing_up() -> None:
    """Stress: a 50-step plan must complete without crashing, without
    runaway memory (records grow linearly), and without budget bugs.
    Real workflows rarely hit 50 steps but the orchestrator should
    handle it gracefully — we don't want a hidden quadratic anywhere."""
    from xpath_healer.orchestrator import TelemetryCounter

    N = 50
    steps_payload = [
        {"step_id": f"step_{i:02d}", "intent": "x", "action": "click", "target_label": "OK"}
        for i in range(N)
    ]
    llm = _ScriptedLLM([
        ChatResponse(tool_calls=[
            ToolCall(id="c", name="commit_plan", arguments={"steps": steps_payload}),
        ])
    ])

    class _OkLocator:
        async def click(self_): return None
        async def scroll_into_view_if_needed(self_, timeout=0): return None
        async def evaluate(self_, script, arg=None): return True

    facade = _FacadeFake(
        recovered=Recovered(
            status="success", correlation_id="c",
            locator_spec=LocatorSpec(kind="xpath", value="//x"),
            runtime_locator=_OkLocator(),
            strategy_id="rules",
        ),
    )
    counter = TelemetryCounter()
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(llm),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        telemetry=counter,
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="50-step run"))
    assert result.status == "success"
    # Every step ran, every step's duration was recorded.
    assert len(result.completed_steps) == N
    assert len(counter.step_durations_ms) == N
    # The heal-strategy counter is N (one per step).
    assert counter.heal_strategy_counts.get("rules") == N


@pytest.mark.asyncio
async def test_long_workflow_budget_caps_hold_under_repeated_failures() -> None:
    """A 50-step plan where EVERY step fails its heal must stop at the
    first failure (one fail-fast exit) instead of burning the entire
    plan budget. Robustness invariant: failures don't compound."""
    N = 50
    steps_payload = [
        {"step_id": f"step_{i:02d}", "intent": "x", "action": "click", "target_label": "OK"}
        for i in range(N)
    ]
    llm = _ScriptedLLM([
        ChatResponse(tool_calls=[
            ToolCall(id="c", name="commit_plan", arguments={"steps": steps_payload}),
        ])
    ])
    facade = _FacadeFake(
        recovered=Recovered(status="failed", correlation_id="c", error="never finds it"),
    )
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(llm),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        max_recovery_inserts=0,  # no inserts → first failure is terminal
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="50-step fail"))
    assert result.status == "failed"
    # We must have stopped at step 1 (index 0), NOT executed all 50.
    assert len(result.completed_steps) == 1


# ---------------------------------------------------------------------------
# Adversarial inputs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decomposer_handles_empty_page_gracefully() -> None:
    """An empty (about:blank-style) page has no outline + no state.
    The decomposer must not crash and must return a plan or empty
    metadata that the orchestrator interprets as failure, not
    exception."""
    from xpath_healer.orchestrator import PageStateObserver

    class _EmptyPage:
        url = "about:blank"
        async def evaluate(self_, script, arg=None):
            # observe() expects a dict shape; about:blank yields ~nothing.
            return None
        async def wait_for_load_state(self_, *a, **k):
            return None

    observer = PageStateObserver()
    state = await observer.observe(_EmptyPage())
    # Must NOT raise; returns empty dict because eval gave None.
    assert state == {}


@pytest.mark.asyncio
async def test_decomposer_handles_js_shell_with_no_dom_gracefully(monkeypatch) -> None:
    """A JS-rendered SPA shell can return an empty outline even after
    networkidle (the page is still mounting React/Vue). The decomposer's
    outline-retry-with-networkidle path should fire once; if the second
    read is still empty, return an empty plan with an explicit error
    in metadata — NOT crash."""
    from xpath_healer.mcp import explorer as exp_mod
    from xpath_healer.orchestrator import decomposer as dcm_mod

    async def fake_outline_always_empty(adapter, page, *, max_chars=8000, focus_text=""):
        return {"outline": "", "total_nodes_emitted": 0}

    monkeypatch.setattr(exp_mod, "_exec_read_outline", fake_outline_always_empty)
    monkeypatch.setattr(dcm_mod, "_exec_read_outline", fake_outline_always_empty)

    class _JsShell:
        async def wait_for_load_state(self_, *a, **k):
            return None
        async def evaluate(self_, script, arg=None):
            return None

    class _LLM(LLMClient):
        async def chat(self_, messages, *, tools=None, temperature=0.0, max_tokens=None):
            # If outline is empty, model has nothing to plan against.
            return ChatResponse(content="", tool_calls=[])

    plan = await AgenticGoalDecomposer(_LLM(), max_attempts=1).decompose(
        goal=WorkflowGoal(text="x"), adapter=_NoOpAdapter(), page=_JsShell(),
    )
    # Empty plan, but no crash. Metadata carries the diagnostic.
    assert plan.steps == []
    assert plan.metadata.get("error")


@pytest.mark.asyncio
async def test_goal_action_unmet_demotes_verify_only_success_to_failed() -> None:
    """Surfaced by adversarial_browser harness on empty_page/captcha_wall:
    the decomposer can plan a verify-only step that auto-passes
    (LLM-tier: "snapshot is empty, indicating no visible elements").
    The orchestrator now demotes such a run to status=failed when
    the goal text explicitly demanded an action."""
    from xpath_healer.orchestrator.models import (
        ExecutionResult, StepRunRecord, VerificationResult,
    )

    # Goal: "Click the Submit button" (demands a click action).
    goal = WorkflowGoal(text="Click the Submit button.")
    # Completed: ONE verify step that "passed" by confirming the page is empty.
    rec = StepRunRecord(step_id="verify_empty", action="verify", target_label="")
    rec.execution = ExecutionResult(status="ok", action="verify")
    rec.verification = VerificationResult(
        ok=True, tier="llm", reason="snapshot is empty", confidence=0.7,
    )
    unmet = WorkflowOrchestrator._goal_action_unmet(goal=goal, completed=[rec])
    assert unmet  # non-empty error string


@pytest.mark.asyncio
async def test_goal_action_unmet_accepts_verify_only_when_goal_is_verification() -> None:
    """A goal that only asks to verify/check should NOT be demoted by
    the new contract — verify-only success is the user's intent."""
    from xpath_healer.orchestrator.models import (
        ExecutionResult, StepRunRecord, VerificationResult,
    )

    goal = WorkflowGoal(text="Verify the page title says 'Login'.")
    rec = StepRunRecord(step_id="vt", action="verify", target_label="")
    rec.execution = ExecutionResult(status="ok", action="verify")
    rec.verification = VerificationResult(
        ok=True, tier="structural", reason="text_visible('Login')=True", confidence=1.0,
    )
    unmet = WorkflowOrchestrator._goal_action_unmet(goal=goal, completed=[rec])
    assert unmet == ""  # empty = no error = success allowed


@pytest.mark.asyncio
async def test_goal_action_unmet_passes_when_real_action_succeeded() -> None:
    """A click goal with a click step that succeeded should NOT be
    demoted — the contract requires AT LEAST ONE successful real
    action, not pure verify."""
    from xpath_healer.orchestrator.models import (
        ExecutionResult, StepRunRecord, VerificationResult,
    )

    goal = WorkflowGoal(text="Click Submit and verify the form posts.")
    click_rec = StepRunRecord(step_id="click_submit", action="click", target_label="Submit")
    click_rec.execution = ExecutionResult(status="ok", action="click")
    click_rec.verification = VerificationResult(
        ok=True, tier="auto", reason="executor ok", confidence=1.0,
    )
    verify_rec = StepRunRecord(step_id="verify_posted", action="verify", target_label="")
    verify_rec.execution = ExecutionResult(status="ok", action="verify")
    verify_rec.verification = VerificationResult(
        ok=True, tier="llm", reason="form posted", confidence=0.9,
    )
    unmet = WorkflowOrchestrator._goal_action_unmet(
        goal=goal, completed=[click_rec, verify_rec]
    )
    assert unmet == ""


@pytest.mark.asyncio
async def test_visual_recovery_proposes_abort_on_captcha_finding() -> None:
    """When vision sees a captcha wall, _proposal_from_vision must
    emit an abort proposal (not insert dismiss-modal, which would loop)."""
    from xpath_healer.core.workflow import REWRITE_ACTION_ABORT, WorkflowStep

    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(
        ok=False,
        finding="cloudflare verify-human wall blocks the page",
        confidence=0.99,
        suggested_action="abort:cloudflare_captcha",
    )
    rec = _step_rec(verify_ok=False, verify_conf=0.4, finding=finding)
    step = WorkflowStep(step_id="s1", intent="x", action="click", target_label="Buy")
    proposal = orch._proposal_from_vision(record=rec, step=step)
    assert proposal is not None
    assert proposal.action == REWRITE_ACTION_ABORT
    # Auto-applied so the orchestrator stops without further prompting.
    assert proposal.auto_applied is True
    assert "cloudflare" in proposal.reason.lower()


def test_vision_does_not_demote_ok_yet() -> None:
    """The current implementation only promotes fail->ok, not ok->fail.
    Documents the gap and locks the safe direction so a future demote
    path is intentional, not accidental."""
    orch = _make_runner(visual_override_threshold=0.8)
    finding = InspectionResult(
        ok=False, finding="captcha showed up after success", confidence=0.99,
        suggested_action="abort:captcha",
    )
    rec = _step_rec(verify_ok=True, verify_conf=0.5, finding=finding)
    # Terminal is already "ok"; the revise helper is a no-op in this direction.
    assert orch._revise_terminal_with_vision(record=rec, terminal="ok") == "ok"
    assert rec.verification.ok is True  # not demoted
