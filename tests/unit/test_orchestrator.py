"""Phase 6 — orchestrator unit tests.

Coverage:
  * models: round-trips + cache_key + action constants
  * AgenticGoalDecomposer: happy path / retry / final failure / plan
    validation rejections
  * PlaywrightActionExecutor: each action verb + error fallback
  * TieredOutcomeVerifier: auto / structural / LLM tiers, executor-error
    short-circuit, no-llm passthrough
  * WorkflowOrchestrator: e2e happy path, navigate-only step, heal
    failure → fail terminal, rewrite skip / abort / insert_before /
    replace, value plumbing into vars / executor
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import LocatorSpec, Recovered
from xpath_healer.core.workflow import (
    REWRITE_ACTION_ABORT,
    REWRITE_ACTION_INSERT_BEFORE,
    REWRITE_ACTION_REPLACE,
    REWRITE_ACTION_SKIP,
    WorkflowRewriteProposal,
    WorkflowStep,
)
from xpath_healer.llm.client import ChatMessage, ChatResponse, LLMClient, ToolCall, ToolDefinition
from xpath_healer.orchestrator import (
    AgenticGoalDecomposer,
    AgenticOutcomeVerifier,
    ExecutionResult,
    OrchestrationResult,
    PlannedWorkflow,
    PlaywrightActionExecutor,
    TieredOutcomeVerifier,
    VerificationResult,
    WorkflowGoal,
    WorkflowOrchestrator,
)
from xpath_healer.orchestrator.models import (
    ACTION_CLICK,
    ACTION_FILL,
    ACTION_NAVIGATE,
    ACTION_SELECT,
    ACTION_VERIFY,
    is_known_action,
)


# ===========================================================================
# Helpers — scripted LLM, fake adapter / locator / page / facade
# ===========================================================================


class _ScriptedLLM(LLMClient):
    def __init__(self, responses: list[ChatResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.calls.append(list(messages))
        if not self._responses:
            return ChatResponse(content="", tool_calls=[])
        return self._responses.pop(0)


class _FakeLocator:
    """RuntimeLocator-shaped fake. Records the actions taken so tests
    can assert."""

    def __init__(self) -> None:
        self.filled: list[str] = []
        self.clicked: int = 0
        self.selected: list[str] = []
        self.evaluates: list[tuple[str, Any]] = []
        # Toggle to force the natural call to raise so we exercise the
        # JS-fallback branch.
        self.fail_natural: bool = False

    async def fill(self, value: str) -> None:
        if self.fail_natural:
            raise RuntimeError("intercepted")
        self.filled.append(value)

    async def click(self) -> None:
        if self.fail_natural:
            raise RuntimeError("intercepted")
        self.clicked += 1

    async def select_option(self, *args, **kwargs) -> None:
        if self.fail_natural:
            raise RuntimeError("no such option")
        if "label" in kwargs:
            self.selected.append(("label", kwargs["label"]))
        elif args:
            self.selected.append(("value", args[0]))

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        self.evaluates.append((script, arg))
        return True


class _FakePage:
    def __init__(self, html: str = "", url: str = "about:blank") -> None:
        self.html = html
        self._url = url
        self.navigated_to: list[str] = []

    @property
    def url(self) -> str:
        return self._url

    async def goto(self, url: str, wait_until: str = "load") -> None:
        self.navigated_to.append(url)
        self._url = url


class _OutlineAdapter:
    """Adapter that returns scripted outlines + a generic locator."""

    name = "outline"

    def __init__(self, outline: str = "form\n  input[name=email]\n  button \"Submit\"",
                 body_text: str = "") -> None:
        self.outline = outline
        self.body_text = body_text

    async def resolve_locator(self, root: Any, spec: LocatorSpec):
        # Return a fake locator whose evaluate emits whichever payload
        # the test needs based on the script's content.
        adapter = self
        outline = self.outline
        body_text = self.body_text

        class _L:
            async def count(self_):
                return 1

            def nth(self_, idx):
                return self_

            async def evaluate(self_, script: str, arg: Any = None) -> Any:
                if "location.href" in script:
                    return "https://demoqa.com/text-box"
                if "document.body" in script:
                    return body_text
                # read_page_outline executor — JS returns an obj with
                # outline/total_nodes_emitted/total_nodes_considered.
                return {
                    "outline": outline,
                    "total_nodes_emitted": 2,
                    "total_nodes_considered": 4,
                    "focus_text": (arg or {}).get("focusText", "") if isinstance(arg, dict) else "",
                }

        return _L()

    async def capture_page_html(self, page: Any) -> str:
        return ""


class _FacadeFake:
    """Just enough surface for the orchestrator: adapter, recover_workflow_step,
    report_step_outcome."""

    def __init__(
        self,
        *,
        adapter: AutomationAdapter,
        recoveries: list[Recovered] | None = None,
        rewrite_proposals: list[WorkflowRewriteProposal | None] | None = None,
    ) -> None:
        self.adapter = adapter
        self._recoveries = list(recoveries or [])
        self._rewrites = list(rewrite_proposals or [])
        self.reported: list[dict[str, Any]] = []
        self.heal_calls: list[dict[str, Any]] = []

    async def recover_workflow_step(self, **kwargs) -> Recovered:
        self.heal_calls.append(kwargs)
        if self._recoveries:
            rec = self._recoveries.pop(0)
        else:
            rec = Recovered(
                status="failed", correlation_id="c", error="no scripted recovery"
            )
        if self._rewrites:
            rec.rewrite_proposal = self._rewrites.pop(0)
        return rec

    async def report_step_outcome(self, **kwargs) -> bool:
        self.reported.append(dict(kwargs))
        return True


def _success_recovery(value: str = "//*[@id='x']") -> Recovered:
    fake = _FakeLocator()
    rec = Recovered(
        status="success",
        correlation_id="c",
        locator_spec=LocatorSpec(kind="xpath", value=value),
        runtime_locator=fake,
        strategy_id="rules",
    )
    return rec


def _failed_recovery() -> Recovered:
    return Recovered(
        status="failed",
        correlation_id="c",
        locator_spec=None,
        error="cascade exhausted",
    )


# ===========================================================================
# 1) Models
# ===========================================================================


def test_workflow_goal_cache_key_is_stable_and_value_sensitive() -> None:
    g1 = WorkflowGoal(text="search mobile", start_url="https://x", values={"q": "mobile"})
    g2 = WorkflowGoal(text="search mobile", start_url="https://x", values={"q": "mobile"})
    g3 = WorkflowGoal(text="search mobile", start_url="https://x", values={"q": "laptop"})
    assert g1.cache_key() == g2.cache_key()
    assert g1.cache_key() != g3.cache_key()
    assert len(g1.cache_key()) == 16


def test_is_known_action_inventory() -> None:
    assert is_known_action(ACTION_NAVIGATE)
    assert is_known_action(ACTION_FILL)
    assert is_known_action(ACTION_CLICK)
    assert is_known_action(ACTION_SELECT)
    assert is_known_action(ACTION_VERIFY)
    assert not is_known_action("drag")
    assert not is_known_action("")


def test_planned_workflow_value_for_returns_default() -> None:
    p = PlannedWorkflow(
        workflow_id="w",
        goal=WorkflowGoal(text="g"),
        steps=[],
        values_by_step={"s1": "alice@example.com"},
    )
    assert p.value_for("s1") == "alice@example.com"
    assert p.value_for("missing") == ""


# ===========================================================================
# 2) AgenticGoalDecomposer
# ===========================================================================


def _commit_plan_response(steps: list[dict[str, Any]]) -> ChatResponse:
    return ChatResponse(
        tool_calls=[
            ToolCall(id="c1", name="commit_plan", arguments={"steps": steps})
        ]
    )


@pytest.mark.asyncio
async def test_decomposer_happy_path_returns_planned_workflow() -> None:
    llm = _ScriptedLLM(
        [
            _commit_plan_response(
                [
                    {
                        "step_id": "fill_email",
                        "intent": "type email",
                        "action": "fill",
                        "target_label": "Email",
                        "value": "alice@example.com",
                        "expected_outcome": "email field shows alice@example.com",
                    },
                    {
                        "step_id": "click_submit",
                        "intent": "click submit",
                        "action": "click",
                        "target_label": "Submit",
                    },
                ]
            )
        ]
    )
    decomp = AgenticGoalDecomposer(llm)
    plan = await decomp.decompose(
        goal=WorkflowGoal(
            text="Sign up with email alice@example.com",
            values={"email": "alice@example.com"},
        ),
        adapter=_OutlineAdapter(),
        page=_FakePage(),
    )
    assert len(plan.steps) == 2
    assert plan.steps[0].step_id == "fill_email"
    assert plan.values_by_step["fill_email"] == "alice@example.com"
    assert plan.metadata["attempts"] == 1
    # prompt was page-grounded
    user_msg = llm.calls[0][1].content
    assert "page_outline" in user_msg


@pytest.mark.asyncio
async def test_decomposer_retries_when_no_commit_plan_call() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(content="I'm thinking...", tool_calls=[]),
            _commit_plan_response(
                [{"step_id": "click_x", "intent": "click", "action": "click", "target_label": "X"}]
            ),
        ]
    )
    decomp = AgenticGoalDecomposer(llm, max_attempts=2)
    plan = await decomp.decompose(
        goal=WorkflowGoal(text="click X"),
        adapter=_OutlineAdapter(),
        page=_FakePage(),
    )
    assert len(plan.steps) == 1
    assert plan.metadata["attempts"] == 2


@pytest.mark.asyncio
async def test_decomposer_returns_empty_plan_when_budget_exhausted() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(content="no commit", tool_calls=[]),
            ChatResponse(content="still no commit", tool_calls=[]),
        ]
    )
    decomp = AgenticGoalDecomposer(llm, max_attempts=2)
    plan = await decomp.decompose(
        goal=WorkflowGoal(text="x"), adapter=_OutlineAdapter(), page=_FakePage()
    )
    assert plan.steps == []
    assert "error" in plan.metadata


@pytest.mark.asyncio
async def test_decomposer_rejects_invalid_action_and_retries() -> None:
    llm = _ScriptedLLM(
        [
            _commit_plan_response(
                [{"step_id": "drag_it", "intent": "drag", "action": "drag", "target_label": "X"}]
            ),
            _commit_plan_response(
                [{"step_id": "click_x", "intent": "click", "action": "click", "target_label": "X"}]
            ),
        ]
    )
    decomp = AgenticGoalDecomposer(llm, max_attempts=2)
    plan = await decomp.decompose(
        goal=WorkflowGoal(text="x"), adapter=_OutlineAdapter(), page=_FakePage()
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].step_id == "click_x"


@pytest.mark.asyncio
async def test_decomposer_rejects_duplicate_step_ids_then_accepts_fixed_plan() -> None:
    """First attempt has duplicate step_id (rejected with structured
    tool-response error); second attempt fixes it and is accepted."""
    llm = _ScriptedLLM(
        [
            _commit_plan_response(
                [
                    {"step_id": "s", "intent": "a", "action": "click", "target_label": "X"},
                    {"step_id": "s", "intent": "b", "action": "click", "target_label": "Y"},
                ]
            ),
            _commit_plan_response(
                [
                    {"step_id": "s1", "intent": "a", "action": "click", "target_label": "X"},
                    {"step_id": "s2", "intent": "b", "action": "click", "target_label": "Y"},
                ]
            ),
        ]
    )
    decomp = AgenticGoalDecomposer(llm, max_attempts=2)
    plan = await decomp.decompose(
        goal=WorkflowGoal(text="x"), adapter=_OutlineAdapter(), page=_FakePage()
    )
    assert [s.step_id for s in plan.steps] == ["s1", "s2"]
    assert plan.metadata["attempts"] == 2
    # The retry path included a "Fix the plan" instruction message — verify it.
    last_call_msgs = llm.calls[-1]
    assert any("Fix the plan" in (m.content or "") for m in last_call_msgs)


@pytest.mark.asyncio
async def test_decomposer_returns_invalid_plan_error_when_retries_exhausted() -> None:
    """All attempts produce duplicate IDs — final metadata flags invalid_plan."""
    bad_plan = [
        {"step_id": "s", "intent": "a", "action": "click", "target_label": "X"},
        {"step_id": "s", "intent": "b", "action": "click", "target_label": "Y"},
    ]
    llm = _ScriptedLLM(
        [_commit_plan_response(bad_plan), _commit_plan_response(bad_plan)]
    )
    decomp = AgenticGoalDecomposer(llm, max_attempts=2)
    plan = await decomp.decompose(
        goal=WorkflowGoal(text="x"), adapter=_OutlineAdapter(), page=_FakePage()
    )
    assert plan.steps == []
    assert "invalid_plan" in plan.metadata.get("error", "")
    assert "duplicate step_id" in plan.metadata.get("error", "")


# ===========================================================================
# 3) PlaywrightActionExecutor
# ===========================================================================


@pytest.mark.asyncio
async def test_executor_fill_uses_natural_api_when_available() -> None:
    loc = _FakeLocator()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="fill", action="fill"),
        locator=loc, page=_FakePage(), value="alice", adapter=_OutlineAdapter(),
    )
    assert res.status == "ok"
    assert loc.filled == ["alice"]
    assert res.page_signal["value_after"] == "alice"


@pytest.mark.asyncio
async def test_executor_fill_falls_back_to_evaluate_on_natural_error() -> None:
    loc = _FakeLocator()
    loc.fail_natural = True
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="fill", action="fill"),
        locator=loc, page=_FakePage(), value="bob", adapter=_OutlineAdapter(),
    )
    assert res.status == "ok"
    assert loc.evaluates  # fell back to JS
    assert loc.filled == []


@pytest.mark.asyncio
async def test_executor_click_natural_then_fallback() -> None:
    loc = _FakeLocator()
    await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="click", action="click"),
        locator=loc, page=_FakePage(), value="", adapter=_OutlineAdapter(),
    )
    assert loc.clicked == 1
    loc2 = _FakeLocator()
    loc2.fail_natural = True
    await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="click", action="click"),
        locator=loc2, page=_FakePage(), value="", adapter=_OutlineAdapter(),
    )
    assert loc2.clicked == 0
    assert loc2.evaluates  # JS fallback


@pytest.mark.asyncio
async def test_executor_select_prefers_label_then_value() -> None:
    loc = _FakeLocator()
    await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="sel", action="select"),
        locator=loc, page=_FakePage(), value="United States", adapter=_OutlineAdapter(),
    )
    assert loc.selected == [("label", "United States")]


@pytest.mark.asyncio
async def test_executor_navigate_via_page_goto() -> None:
    page = _FakePage()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="go", action="navigate"),
        locator=None, page=page, value="https://example.com",
        adapter=_OutlineAdapter(),
    )
    assert res.status == "ok"
    assert page.navigated_to == ["https://example.com"]


@pytest.mark.asyncio
async def test_executor_verify_only_step_returns_ok_no_op() -> None:
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="check", action="verify"),
        locator=None, page=_FakePage(), value="", adapter=_OutlineAdapter(),
    )
    assert res.status == "ok"
    assert "no action" in res.detail


@pytest.mark.asyncio
async def test_executor_unsupported_action_returns_error() -> None:
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="drag", action="drag"),
        locator=_FakeLocator(), page=_FakePage(), value="",
        adapter=_OutlineAdapter(),
    )
    assert res.status == "error"
    assert "unsupported" in res.detail


# ===========================================================================
# 4) TieredOutcomeVerifier
# ===========================================================================


@pytest.mark.asyncio
async def test_verifier_short_circuits_on_executor_error() -> None:
    v = TieredOutcomeVerifier(llm_verifier=None)
    res = await v.verify(
        step=WorkflowStep(step_id="s", intent="i", action="fill", expected_outcome="anything"),
        execution=ExecutionResult(status="error", action="fill", detail="boom"),
        adapter=_OutlineAdapter(), page=_FakePage(),
    )
    assert res.ok is False
    assert res.tier == "auto"
    assert "executor_error" in res.reason


@pytest.mark.asyncio
async def test_verifier_auto_pass_when_no_expected_outcome() -> None:
    v = TieredOutcomeVerifier(llm_verifier=None)
    res = await v.verify(
        step=WorkflowStep(step_id="s", intent="i", action="fill"),
        execution=ExecutionResult(status="ok", action="fill"),
        adapter=_OutlineAdapter(), page=_FakePage(),
    )
    assert res.ok is True
    assert res.tier == "auto"


@pytest.mark.asyncio
async def test_verifier_auto_pass_when_value_after_matches_expected() -> None:
    v = TieredOutcomeVerifier(llm_verifier=None)
    res = await v.verify(
        step=WorkflowStep(
            step_id="s", intent="i", action="fill",
            expected_outcome="email field shows alice@example.com",
        ),
        execution=ExecutionResult(
            status="ok", action="fill",
            page_signal={"value_after": "alice@example.com"},
        ),
        adapter=_OutlineAdapter(), page=_FakePage(),
    )
    assert res.ok is True
    assert res.tier == "auto"


@pytest.mark.asyncio
async def test_verifier_structural_url_contains_pass() -> None:
    v = TieredOutcomeVerifier(llm_verifier=None)
    res = await v.verify(
        step=WorkflowStep(
            step_id="s", intent="nav", action="navigate",
            expected_outcome="URL contains text-box",
        ),
        execution=ExecutionResult(status="ok", action="navigate"),
        adapter=_OutlineAdapter(),  # adapter returns url=https://demoqa.com/text-box
        page=_FakePage(url="https://demoqa.com/text-box"),
    )
    assert res.tier == "structural"
    assert res.ok is True


@pytest.mark.asyncio
async def test_verifier_structural_text_visible_pass() -> None:
    adapter = _OutlineAdapter(body_text="You have selected: Home Desktop")
    v = TieredOutcomeVerifier(llm_verifier=None)
    res = await v.verify(
        step=WorkflowStep(
            step_id="s", intent="check", action="verify",
            expected_outcome="see 'Desktop' visible",
        ),
        execution=ExecutionResult(status="ok", action="verify"),
        adapter=adapter, page=_FakePage(),
    )
    assert res.tier == "structural"
    assert res.ok is True


@pytest.mark.asyncio
async def test_verifier_falls_through_to_llm_for_semantic_claim() -> None:
    llm = _ScriptedLLM(
        [ChatResponse(content='{"ok": true, "reason": "page shows mobiles", "confidence": 0.92}')]
    )
    v = TieredOutcomeVerifier(llm_verifier=AgenticOutcomeVerifier(llm))
    res = await v.verify(
        step=WorkflowStep(
            step_id="s", intent="filter", action="click",
            expected_outcome="results show only mobiles under 50000",
        ),
        execution=ExecutionResult(status="ok", action="click"),
        adapter=_OutlineAdapter(), page=_FakePage(),
    )
    assert res.tier == "llm"
    assert res.ok is True
    # LLM verifier caps its emitted confidence at 0.85 (it sees a
    # compressed text snapshot, not pixels; vision-tier override at
    # 0.8 must still be able to win on disagreement).
    assert res.confidence == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_verifier_without_llm_falls_through_passthrough() -> None:
    v = TieredOutcomeVerifier(llm_verifier=None)
    res = await v.verify(
        step=WorkflowStep(
            step_id="s", intent="filter", action="click",
            expected_outcome="results show mobiles",
        ),
        execution=ExecutionResult(status="ok", action="click"),
        adapter=_OutlineAdapter(), page=_FakePage(),
    )
    # No LLM configured → cascaded passthrough (orchestrator continues).
    assert res.ok is True
    assert res.tier == "auto"
    assert res.confidence == 0.5


@pytest.mark.asyncio
async def test_verifier_llm_parses_messy_response() -> None:
    # Some models wrap JSON in prose; verifier extracts the {...} block.
    llm = _ScriptedLLM(
        [ChatResponse(content='Sure! Here you go:\n{"ok": false, "reason": "not visible"}\nThanks.')]
    )
    v = TieredOutcomeVerifier(llm_verifier=AgenticOutcomeVerifier(llm))
    res = await v.verify(
        step=WorkflowStep(step_id="s", intent="i", action="click", expected_outcome="semantic"),
        execution=ExecutionResult(status="ok", action="click"),
        adapter=_OutlineAdapter(), page=_FakePage(),
    )
    assert res.tier == "llm"
    assert res.ok is False
    assert res.reason == "not visible"


# ===========================================================================
# 5) WorkflowOrchestrator (end-to-end with mocks)
# ===========================================================================


@pytest.mark.asyncio
async def test_orchestrator_happy_path_runs_all_steps() -> None:
    # Plan: fill email + click submit
    llm = _ScriptedLLM(
        [
            _commit_plan_response(
                [
                    {
                        "step_id": "fill_email",
                        "intent": "type email",
                        "action": "fill",
                        "target_label": "Email",
                        "value": "alice@example.com",
                        "expected_outcome": "email field shows alice@example.com",
                    },
                    {
                        "step_id": "click_submit",
                        "intent": "submit",
                        "action": "click",
                        "target_label": "Submit",
                    },
                ]
            )
        ]
    )
    decomp = AgenticGoalDecomposer(llm)
    facade = _FacadeFake(
        adapter=_OutlineAdapter(),
        recoveries=[_success_recovery(), _success_recovery()],
    )
    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=decomp,
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    result = await orch.run(
        page=_FakePage(),
        goal=WorkflowGoal(text="sign up alice", values={"email": "alice@example.com"}),
    )
    assert result.status == "success"
    assert len(result.completed_steps) == 2
    assert result.completed_steps[0].step_id == "fill_email"
    # report_step_outcome closed the loop for both steps.
    assert len(facade.reported) == 2


@pytest.mark.asyncio
async def test_orchestrator_navigates_to_start_url_first() -> None:
    llm = _ScriptedLLM(
        [
            _commit_plan_response(
                [{"step_id": "click_x", "intent": "click", "action": "click", "target_label": "X"}]
            )
        ]
    )
    decomp = AgenticGoalDecomposer(llm)
    facade = _FacadeFake(adapter=_OutlineAdapter(), recoveries=[_success_recovery()])
    page = _FakePage()
    orch = WorkflowOrchestrator(
        facade=facade, decomposer=decomp, executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    await orch.run(
        page=page,
        goal=WorkflowGoal(text="click", start_url="https://demoqa.com/text-box"),
    )
    assert page.navigated_to == ["https://demoqa.com/text-box"]


@pytest.mark.asyncio
async def test_orchestrator_returns_failed_when_decomposer_returns_no_steps() -> None:
    llm = _ScriptedLLM([ChatResponse(content="nope", tool_calls=[])])
    decomp = AgenticGoalDecomposer(llm, max_attempts=1)
    facade = _FacadeFake(adapter=_OutlineAdapter())
    orch = WorkflowOrchestrator(
        facade=facade, decomposer=decomp, executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="x"))
    assert result.status == "failed"
    assert "decomposer_produced_no_steps" in result.metadata.get("error", "")


@pytest.mark.asyncio
async def test_orchestrator_failed_heal_with_no_proposal_yields_failed() -> None:
    llm = _ScriptedLLM(
        [_commit_plan_response([{"step_id": "click_x", "intent": "i", "action": "click", "target_label": "X"}])]
    )
    facade = _FacadeFake(
        adapter=_OutlineAdapter(),
        recoveries=[_failed_recovery()],
        rewrite_proposals=[None],
    )
    orch = WorkflowOrchestrator(
        facade=facade, decomposer=AgenticGoalDecomposer(llm),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="x"))
    assert result.status == "failed"
    assert result.failed_step is not None
    assert result.failed_step.heal_status == "failed"


@pytest.mark.asyncio
async def test_orchestrator_rewrite_skip_on_optional_step_continues() -> None:
    llm = _ScriptedLLM(
        [
            _commit_plan_response(
                [
                    {
                        "step_id": "click_banner",
                        "intent": "dismiss banner",
                        "action": "click",
                        "target_label": "Accept",
                        "optional": True,
                    },
                    {
                        "step_id": "click_submit",
                        "intent": "submit",
                        "action": "click",
                        "target_label": "Submit",
                    },
                ]
            )
        ]
    )
    facade = _FacadeFake(
        adapter=_OutlineAdapter(),
        recoveries=[_failed_recovery(), _success_recovery()],
        rewrite_proposals=[
            WorkflowRewriteProposal(action=REWRITE_ACTION_SKIP, reason="banner gone", confidence=0.9),
            None,
        ],
    )
    orch = WorkflowOrchestrator(
        facade=facade, decomposer=AgenticGoalDecomposer(llm),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="dismiss + submit"))
    assert result.status == "success"
    assert len(result.completed_steps) == 2
    assert result.completed_steps[0].rewrite_applied == REWRITE_ACTION_SKIP


@pytest.mark.asyncio
async def test_orchestrator_rewrite_abort_terminates_with_aborted_status() -> None:
    llm = _ScriptedLLM(
        [_commit_plan_response([{"step_id": "click_x", "intent": "i", "action": "click", "target_label": "X"}])]
    )
    facade = _FacadeFake(
        adapter=_OutlineAdapter(),
        recoveries=[_failed_recovery()],
        rewrite_proposals=[WorkflowRewriteProposal(action=REWRITE_ACTION_ABORT, reason="dead", confidence=1.0)],
    )
    orch = WorkflowOrchestrator(
        facade=facade, decomposer=AgenticGoalDecomposer(llm),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="x"))
    assert result.status == "aborted"
    assert result.failed_step is not None
    assert result.failed_step.rewrite_applied == REWRITE_ACTION_ABORT


@pytest.mark.asyncio
async def test_orchestrator_rewrite_insert_before_inserts_and_retries() -> None:
    """Heal fails → rewriter proposes insert_before → orchestrator inserts
    new step, then retries the original which now succeeds."""
    llm = _ScriptedLLM(
        [_commit_plan_response([{"step_id": "click_target", "intent": "i", "action": "click", "target_label": "Target"}])]
    )
    inserted_step = WorkflowStep(
        step_id="solve_captcha",
        intent="captcha appeared",
        action="click",
        target_label="I am not a robot",
    )
    facade = _FacadeFake(
        adapter=_OutlineAdapter(),
        recoveries=[
            _failed_recovery(),      # original target heal fails
            _success_recovery(),     # inserted step heals
            _success_recovery(),     # retry of original target succeeds
        ],
        rewrite_proposals=[
            WorkflowRewriteProposal(
                action=REWRITE_ACTION_INSERT_BEFORE,
                reason="captcha appeared",
                confidence=0.95,
                new_step=inserted_step,
            ),
            None,
            None,
        ],
    )
    orch = WorkflowOrchestrator(
        facade=facade, decomposer=AgenticGoalDecomposer(llm),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
        max_recovery_inserts=2,
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="click target"))
    assert result.status == "success"
    # Three records: target failed-with-insert, inserted step ok, target retry ok.
    assert len(result.completed_steps) == 3
    assert result.completed_steps[0].rewrite_applied == REWRITE_ACTION_INSERT_BEFORE
    assert result.completed_steps[1].step_id == "solve_captcha"
    assert result.completed_steps[2].step_id == "click_target"


@pytest.mark.asyncio
async def test_orchestrator_rewrite_replace_swaps_current_step() -> None:
    """Heal fails → rewriter proposes replace → current step is replaced
    with new_step (original dropped); new step then runs."""
    llm = _ScriptedLLM(
        [_commit_plan_response([{"step_id": "pick_radio", "intent": "i", "action": "click", "target_label": "Yes"}])]
    )
    new_step = WorkflowStep(
        step_id="pick_dropdown",
        intent="dropdown replaced radio",
        action="select",
        target_label="Confirmation",
    )
    facade = _FacadeFake(
        adapter=_OutlineAdapter(),
        recoveries=[_failed_recovery(), _success_recovery()],
        rewrite_proposals=[
            WorkflowRewriteProposal(
                action=REWRITE_ACTION_REPLACE,
                reason="radio became dropdown",
                confidence=0.9,
                new_step=new_step,
            ),
            None,
        ],
    )
    orch = WorkflowOrchestrator(
        facade=facade, decomposer=AgenticGoalDecomposer(llm),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    result = await orch.run(page=_FakePage(), goal=WorkflowGoal(text="pick"))
    assert result.status == "success"
    assert any(r.step_id == "pick_dropdown" for r in result.completed_steps)


@pytest.mark.asyncio
async def test_orchestrator_threads_value_into_vars_for_fill() -> None:
    llm = _ScriptedLLM(
        [
            _commit_plan_response(
                [
                    {
                        "step_id": "fill_email",
                        "intent": "i",
                        "action": "fill",
                        "target_label": "Email",
                        "value": "alice@example.com",
                    }
                ]
            )
        ]
    )
    facade = _FacadeFake(adapter=_OutlineAdapter(), recoveries=[_success_recovery()])
    orch = WorkflowOrchestrator(
        facade=facade, decomposer=AgenticGoalDecomposer(llm),
        executor=PlaywrightActionExecutor(),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )
    await orch.run(page=_FakePage(), goal=WorkflowGoal(text="fill email"))
    heal_kwargs = facade.heal_calls[0]
    assert heal_kwargs["vars"]["label"] == "Email"
    assert heal_kwargs["vars"]["value_hint"] == "alice@example.com"
