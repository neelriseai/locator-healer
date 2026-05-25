"""Phase 5 additions — single test module covering five orthogonal pieces:

* page-signature hashing + replay gating
* expanded rewrite actions (insert_before / replace)
* auto-apply safety gate
* Postgres workflow-run repo (asyncpg fully mocked)
* Playwright MCP server explorer (MCP client + LLM mocked)
* Appium adapter + facade (fake driver)
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from xpath_healer.api.base import BaseHealerFacade
from xpath_healer.core.healing_service import HealingService
from xpath_healer.core.models import BuildInput, Intent, LocatorSpec, Recovered
from xpath_healer.core.page_signature import compute_page_signature_hash
from xpath_healer.core.workflow import (
    AutoApplyPolicy,
    REWRITE_ACTION_ABORT,
    REWRITE_ACTION_INSERT_BEFORE,
    REWRITE_ACTION_REPLACE,
    REWRITE_ACTION_SKIP,
    STEP_STATUS_HEAL_SUCCEEDED,
    STEP_STATUS_STEP_SUCCEEDED,
    StepRun,
    WorkflowContext,
    WorkflowRewriteProposal,
    WorkflowStep,
    action_requires_new_step,
    is_supported_rewrite_action,
)
from xpath_healer.llm.client import ChatMessage, ChatResponse, LLMClient, ToolCall, ToolDefinition
from xpath_healer.mcp import PlaywrightMCPServerExplorer
from xpath_healer.store.workflow_run_repository import InMemoryWorkflowRunRepository
from xpath_healer.workflow import AgenticWorkflowRewriter


# ===========================================================================
# 1) Page-signature hashing
# ===========================================================================


def test_page_signature_empty_input_returns_empty() -> None:
    assert compute_page_signature_hash(None) == ""
    assert compute_page_signature_hash("") == ""


def test_page_signature_stable_for_same_structure() -> None:
    h1 = compute_page_signature_hash('<form><input data-testid="email" type="email"></form>')
    h2 = compute_page_signature_hash('<form>\n  <input data-testid="email" type="email">\n</form>')
    assert h1 == h2  # whitespace doesn't matter
    assert len(h1) == 16


def test_page_signature_changes_when_stable_attrs_change() -> None:
    h1 = compute_page_signature_hash('<input data-testid="email">')
    h2 = compute_page_signature_hash('<input data-testid="username">')
    assert h1 != h2


def test_page_signature_ignores_volatile_attrs() -> None:
    h1 = compute_page_signature_hash('<input data-testid="email" class="x-123">')
    h2 = compute_page_signature_hash('<input data-testid="email" class="x-456">')
    # `class` is not in the stable set → hashes should match.
    assert h1 == h2


# ===========================================================================
# 2) Replay stage uses signature scoring
# ===========================================================================


class _SnapShotter:
    def __init__(self, html: str) -> None:
        self._html = html

    async def capture(self, page: Any) -> str:
        return self._html


class _CtxForReplay:
    def __init__(self, repo: object | None, html: str) -> None:
        self.workflow_run_repository = repo
        self.dom_snapshotter = _SnapShotter(html)
        self.logger = logging.getLogger("test.phase5.replay")


def _replay_input() -> BuildInput:
    return BuildInput(
        page=object(),
        app_id="a",
        page_name="signup",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        intent=Intent(label="Email"),
        workflow_context=WorkflowContext(
            workflow_id="signup",
            workflow_intent="x",
            current_step=WorkflowStep(step_id="s1", intent="i", action="fill"),
        ),
    )


@pytest.mark.asyncio
async def test_replay_signature_match_yields_top_tier_score() -> None:
    repo = InMemoryWorkflowRunRepository()
    sig = compute_page_signature_hash('<input data-testid="email">')
    await repo.record_step(
        StepRun(
            workflow_id="signup",
            step_id="s1",
            status=STEP_STATUS_STEP_SUCCEEDED,
            locator_used={"kind": "xpath", "value": "//*[@id='email']"},
            page_signature_hash=sig,
        )
    )
    ctx = _CtxForReplay(repo, '<input data-testid="email">')
    out = await HealingService(builder=None)._workflow_replay_candidates(ctx, _replay_input())
    assert len(out) == 1
    assert out[0].score == 0.98
    assert out[0].details["signature_status"] == "match"


@pytest.mark.asyncio
async def test_replay_signature_mismatch_downgrades_score() -> None:
    repo = InMemoryWorkflowRunRepository()
    await repo.record_step(
        StepRun(
            workflow_id="signup",
            step_id="s1",
            status=STEP_STATUS_STEP_SUCCEEDED,
            locator_used={"kind": "xpath", "value": "//*[@id='email']"},
            page_signature_hash="0000aaaaaaaaaaaa",  # known-different
        )
    )
    ctx = _CtxForReplay(repo, '<input data-testid="email">')
    out = await HealingService(builder=None)._workflow_replay_candidates(ctx, _replay_input())
    assert len(out) == 1
    assert out[0].score == 0.75  # step + mismatch
    assert out[0].details["signature_status"] == "mismatch"


@pytest.mark.asyncio
async def test_replay_unknown_signature_uses_legacy_tier() -> None:
    repo = InMemoryWorkflowRunRepository()
    await repo.record_step(
        StepRun(
            workflow_id="signup",
            step_id="s1",
            status=STEP_STATUS_HEAL_SUCCEEDED,
            locator_used={"kind": "xpath", "value": "//*[@id='email']"},
            page_signature_hash="",  # no recorded signature
        )
    )
    ctx = _CtxForReplay(repo, '<input data-testid="email">')
    out = await HealingService(builder=None)._workflow_replay_candidates(ctx, _replay_input())
    assert len(out) == 1
    assert out[0].score == 0.70  # heal + unknown
    assert out[0].details["signature_status"] == "unknown"


# ===========================================================================
# 3) Expanded rewrite actions
# ===========================================================================


def test_supported_actions_include_insert_replace() -> None:
    assert is_supported_rewrite_action(REWRITE_ACTION_INSERT_BEFORE)
    assert is_supported_rewrite_action(REWRITE_ACTION_REPLACE)
    assert is_supported_rewrite_action(REWRITE_ACTION_SKIP)
    assert is_supported_rewrite_action(REWRITE_ACTION_ABORT)
    assert not is_supported_rewrite_action("nope")


def test_action_requires_new_step_for_insert_and_replace() -> None:
    assert action_requires_new_step(REWRITE_ACTION_INSERT_BEFORE)
    assert action_requires_new_step(REWRITE_ACTION_REPLACE)
    assert not action_requires_new_step(REWRITE_ACTION_SKIP)
    assert not action_requires_new_step(REWRITE_ACTION_ABORT)


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


class _NoopAdapter:
    name = "noop"

    async def resolve_locator(self, root, locator_spec):
        class _L:
            async def count(self):
                return 0

            def nth(self, idx):
                return self

            async def evaluate(self, script, arg=None):
                return None

        return _L()

    async def capture_page_html(self, page):
        return ""


def _wf_inp() -> BuildInput:
    return BuildInput(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        intent=Intent(label="Email"),
        workflow_context=WorkflowContext(
            workflow_id="w",
            workflow_intent="i",
            current_step=WorkflowStep(step_id="s1", intent="i", action="fill"),
        ),
    )


@pytest.mark.asyncio
async def test_rewriter_commits_insert_before_with_new_step() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_insert_before",
                        arguments={
                            "reason": "captcha appeared",
                            "confidence": 0.9,
                            "new_step": {
                                "step_id": "captcha_solve",
                                "intent": "solve captcha",
                                "action": "click",
                                "target_label": "I am not a robot",
                                "target_kind": "checkbox",
                            },
                        },
                    )
                ]
            )
        ]
    )
    result = await AgenticWorkflowRewriter(llm).rewrite(
        _NoopAdapter(), object(), _wf_inp(), None, cascade_error=""
    )
    assert result.proposal is not None
    assert result.proposal.action == REWRITE_ACTION_INSERT_BEFORE
    assert result.proposal.new_step is not None
    assert result.proposal.new_step.step_id == "captcha_solve"


@pytest.mark.asyncio
async def test_rewriter_rejects_insert_without_new_step_and_recovers() -> None:
    llm = _ScriptedLLM(
        [
            # Bad commit: missing new_step → server tool response error.
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_insert_before",
                        arguments={"reason": "x", "confidence": 0.9},
                    )
                ]
            ),
            # Model retries with valid abort instead.
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c2",
                        name="commit_abort",
                        arguments={"reason": "cannot recover", "confidence": 0.7},
                    )
                ]
            ),
        ]
    )
    result = await AgenticWorkflowRewriter(llm).rewrite(
        _NoopAdapter(), object(), _wf_inp(), None, cascade_error=""
    )
    assert result.proposal is not None
    assert result.proposal.action == REWRITE_ACTION_ABORT


@pytest.mark.asyncio
async def test_rewriter_rejects_insert_with_incomplete_new_step() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_insert_before",
                        arguments={
                            "reason": "x",
                            "confidence": 0.9,
                            "new_step": {"step_id": "", "intent": "", "action": ""},
                        },
                    )
                ]
            ),
        ]
    )
    result = await AgenticWorkflowRewriter(llm).rewrite(
        _NoopAdapter(), object(), _wf_inp(), None, cascade_error=""
    )
    assert result.proposal is None  # incomplete new_step → no commit


# ===========================================================================
# 4) Auto-apply safety gate
# ===========================================================================


def test_auto_apply_policy_round_trip_and_disabled() -> None:
    p = AutoApplyPolicy(
        allowed_actions=frozenset({REWRITE_ACTION_SKIP}),
        min_confidence=0.9,
        min_prior_confirmations=2,
    )
    revived = AutoApplyPolicy.from_dict(p.to_dict())
    assert revived.allowed_actions == p.allowed_actions
    assert revived.min_confidence == p.min_confidence
    assert revived.min_prior_confirmations == p.min_prior_confirmations
    # Disabled policy should never auto-apply.
    disabled = AutoApplyPolicy.disabled()
    assert disabled.min_confidence > 1.0
    assert disabled.allowed_actions == frozenset()


class _StubRewriter:
    def __init__(self, proposal: WorkflowRewriteProposal | None) -> None:
        self._proposal = proposal

    async def rewrite(self, adapter, page, inp, existing_meta, cascade_error):
        class _R:
            def __init__(self, p):
                self.proposal = p
                self.rounds = 1
                self.tool_calls_made = 1
                self.metadata: dict[str, Any] = {}

        return _R(self._proposal)


class _AutoApplyFacade(BaseHealerFacade):
    def __init__(self, *, proposal, repo) -> None:
        self.logger = logging.getLogger("test.phase5.gate")
        self.adapter = _NoopAdapter()
        self.workflow_run_repository = repo
        self.workflow_rewriter = _StubRewriter(proposal)
        self.snapshotter = None
        self.ctx = None

        class _FakeHealing:
            async def recover_locator(self, ctx, build_input):
                return Recovered(status="failed", correlation_id="c", error="all stages failed")

        self.healing_service = _FakeHealing()


def _wf_context() -> WorkflowContext:
    return WorkflowContext(
        workflow_id="w",
        workflow_intent="i",
        current_step=WorkflowStep(step_id="s1", intent="i", action="fill"),
    )


@pytest.mark.asyncio
async def test_auto_apply_gate_sets_true_when_policy_met() -> None:
    proposal = WorkflowRewriteProposal(
        action=REWRITE_ACTION_SKIP, reason="r", confidence=0.97
    )
    facade = _AutoApplyFacade(proposal=proposal, repo=None)
    out = await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
        auto_apply_policy=AutoApplyPolicy(
            allowed_actions=frozenset({REWRITE_ACTION_SKIP}),
            min_confidence=0.95,
            min_prior_confirmations=0,
        ),
    )
    assert out.rewrite_proposal is not None
    assert out.rewrite_proposal.auto_applied is True
    assert out.status == "failed"  # never mutated


@pytest.mark.asyncio
async def test_auto_apply_gate_blocks_disallowed_action() -> None:
    proposal = WorkflowRewriteProposal(
        action=REWRITE_ACTION_ABORT, reason="r", confidence=0.99
    )
    facade = _AutoApplyFacade(proposal=proposal, repo=None)
    out = await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
        auto_apply_policy=AutoApplyPolicy(
            allowed_actions=frozenset({REWRITE_ACTION_SKIP}),  # abort NOT allowed
            min_confidence=0.5,
        ),
    )
    assert out.rewrite_proposal.auto_applied is False


@pytest.mark.asyncio
async def test_auto_apply_gate_blocks_below_min_confidence() -> None:
    proposal = WorkflowRewriteProposal(
        action=REWRITE_ACTION_SKIP, reason="r", confidence=0.50
    )
    facade = _AutoApplyFacade(proposal=proposal, repo=None)
    out = await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
        auto_apply_policy=AutoApplyPolicy(
            allowed_actions=frozenset({REWRITE_ACTION_SKIP}),
            min_confidence=0.95,
        ),
    )
    assert out.rewrite_proposal.auto_applied is False


@pytest.mark.asyncio
async def test_auto_apply_gate_requires_prior_confirmations() -> None:
    repo = InMemoryWorkflowRunRepository()
    proposal = WorkflowRewriteProposal(
        action=REWRITE_ACTION_SKIP, reason="r", confidence=0.99
    )
    facade = _AutoApplyFacade(proposal=proposal, repo=repo)
    # Without confirmations, gate blocks.
    out = await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
        auto_apply_policy=AutoApplyPolicy(
            allowed_actions=frozenset({REWRITE_ACTION_SKIP}),
            min_confidence=0.95,
            min_prior_confirmations=2,
        ),
    )
    assert out.rewrite_proposal.auto_applied is False

    # Seed two confirmed-skip records.
    for _ in range(2):
        await repo.record_step(
            StepRun(
                workflow_id="w",
                step_id="s1",
                status=STEP_STATUS_STEP_SUCCEEDED,
                note="auto_applied:skip",
            )
        )
    out = await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
        auto_apply_policy=AutoApplyPolicy(
            allowed_actions=frozenset({REWRITE_ACTION_SKIP}),
            min_confidence=0.95,
            min_prior_confirmations=2,
        ),
    )
    assert out.rewrite_proposal.auto_applied is True


@pytest.mark.asyncio
async def test_no_policy_means_no_auto_apply_flag_set() -> None:
    proposal = WorkflowRewriteProposal(
        action=REWRITE_ACTION_SKIP, reason="r", confidence=0.99
    )
    facade = _AutoApplyFacade(proposal=proposal, repo=None)
    out = await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
    )
    assert out.rewrite_proposal.auto_applied is False


# ===========================================================================
# 5) Playwright MCP server explorer — wire layer is mocked
# ===========================================================================


class _FakeMCPSession:
    def __init__(self, tool_results: dict[str, Any]) -> None:
        self._tool_results = tool_results
        self.called: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        self.called.append((name, dict(args)))

        class _R:
            def __init__(self, payload):
                class _C:
                    def __init__(self, t):
                        self.text = t

                self.content = [_C(str(payload))]

        return _R(self._tool_results.get(name, "ok"))


@pytest.mark.asyncio
async def test_playwright_mcp_server_explorer_uses_server_tools_then_commits() -> None:
    fake_session = _FakeMCPSession({"browser_snapshot": "page snapshot text"})

    class _ExplorerForTest(PlaywrightMCPServerExplorer):
        async def _connect(self):
            return {
                "session": fake_session,
                "transport_cm": None,
                "server_tools": [
                    {
                        "name": "browser_snapshot",
                        "description": "snapshot",
                        "input_schema": {"type": "object", "properties": {}},
                    },
                ],
            }

        async def _disconnect(self, client):
            return None

    # LLM: first turn calls browser_snapshot; second turn commits.
    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(id="t1", name="browser_snapshot", arguments={})
                ]
            ),
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_locator",
                        arguments={
                            "xpath": "//button[@id='save']",
                            "reason": "stable id",
                            "confidence": 0.9,
                        },
                    )
                ]
            ),
        ]
    )
    explorer = _ExplorerForTest(llm)
    inp = _wf_inp()
    result = await explorer.explore(_NoopAdapter(), object(), inp, None)
    assert len(result.locators) == 1
    assert result.locators[0].value == "//button[@id='save']"
    assert any(c[0] == "browser_snapshot" for c in fake_session.called)
    assert result.metadata.get("server") == "playwright_mcp"


@pytest.mark.asyncio
async def test_playwright_mcp_server_explorer_returns_empty_on_connect_failure() -> None:
    class _BadExplorer(PlaywrightMCPServerExplorer):
        async def _connect(self):
            raise RuntimeError("mcp SDK missing")

    explorer = _BadExplorer(_ScriptedLLM([]))
    result = await explorer.explore(_NoopAdapter(), object(), _wf_inp(), None)
    assert result.locators == []
    assert result.metadata.get("server") == "unavailable"


# ===========================================================================
# 6) Appium adapter — fake driver
# ===========================================================================


class _FakeAppiumElement:
    def __init__(
        self,
        *,
        text: str = "",
        attrs: dict[str, str] | None = None,
        displayed: bool = True,
        enabled: bool = True,
        location: dict[str, float] | None = None,
        size: dict[str, float] | None = None,
    ) -> None:
        self.text = text
        self._attrs = attrs or {}
        self._displayed = displayed
        self._enabled = enabled
        self.location = location or {"x": 1.0, "y": 2.0}
        self.size = size or {"width": 100.0, "height": 50.0}

    def get_attribute(self, name: str) -> str:
        return self._attrs.get(name, "")

    def is_displayed(self) -> bool:
        return self._displayed

    def is_enabled(self) -> bool:
        return self._enabled


class _FakeAppiumDriver:
    def __init__(self) -> None:
        self.recipe: dict[tuple[str, str], list[_FakeAppiumElement]] = {}
        self.scripts_run: list[str] = []
        self.page_source = "<hierarchy/>"

    def add(self, by: str, value: str, elements: list[_FakeAppiumElement]) -> None:
        self.recipe[(by, value)] = elements

    def find_elements(self, by: str, value: str) -> list[_FakeAppiumElement]:
        return list(self.recipe.get((by, value), []))

    def execute_script(self, script: str, *args: Any) -> Any:
        self.scripts_run.append(script)
        return "ok"


@pytest.mark.asyncio
async def test_appium_adapter_translates_locator_kinds() -> None:
    from adapters.appium_python.adapter import AppiumPythonAdapter

    driver = _FakeAppiumDriver()
    el = _FakeAppiumElement(text="hello")
    # XPath
    driver.add("xpath", "//x", [el])
    # accessibility id
    driver.add("accessibility id", "Save", [el])
    adapter = AppiumPythonAdapter()

    loc_xpath = await adapter.resolve_locator(driver, LocatorSpec(kind="xpath", value="//x"))
    assert await loc_xpath.count() == 1

    loc_role = await adapter.resolve_locator(driver, LocatorSpec(kind="role", value="Save"))
    assert await loc_role.count() == 1


@pytest.mark.asyncio
async def test_appium_evaluate_returns_none_for_js_arrow_script() -> None:
    from adapters.appium_python.adapter import AppiumPythonAdapter

    driver = _FakeAppiumDriver()
    driver.add("xpath", "//x", [_FakeAppiumElement()])
    adapter = AppiumPythonAdapter()
    loc = await adapter.resolve_locator(driver, LocatorSpec(kind="xpath", value="//x"))
    # Web-style JS arrow → mobile has no JS engine → None (graceful).
    assert await loc.evaluate("el => el.value") is None
    assert driver.scripts_run == []  # never called execute_script


@pytest.mark.asyncio
async def test_appium_evaluate_forwards_mobile_scripts() -> None:
    from adapters.appium_python.adapter import AppiumPythonAdapter

    driver = _FakeAppiumDriver()
    driver.add("xpath", "//x", [_FakeAppiumElement()])
    adapter = AppiumPythonAdapter()
    loc = await adapter.resolve_locator(driver, LocatorSpec(kind="xpath", value="//x"))
    result = await loc.evaluate("mobile: scroll")
    assert result == "ok"
    assert driver.scripts_run == ["mobile: scroll"]


@pytest.mark.asyncio
async def test_appium_bounding_box_uses_location_and_size() -> None:
    from adapters.appium_python.adapter import AppiumPythonAdapter

    driver = _FakeAppiumDriver()
    driver.add(
        "xpath",
        "//x",
        [_FakeAppiumElement(location={"x": 10.0, "y": 20.0}, size={"width": 40.0, "height": 60.0})],
    )
    adapter = AppiumPythonAdapter()
    loc = await adapter.resolve_locator(driver, LocatorSpec(kind="xpath", value="//x"))
    bbox = await loc.bounding_box()
    assert bbox == {"x": 10.0, "y": 20.0, "width": 40.0, "height": 60.0}


@pytest.mark.asyncio
async def test_appium_capture_page_html_returns_page_source() -> None:
    from adapters.appium_python.adapter import AppiumPythonAdapter

    driver = _FakeAppiumDriver()
    driver.page_source = "<hierarchy><AppiumElement/></hierarchy>"
    html = await AppiumPythonAdapter().capture_page_html(driver)
    assert html == "<hierarchy><AppiumElement/></hierarchy>"


@pytest.mark.asyncio
async def test_appium_facade_pre_wires_adapter() -> None:
    """The convenience facade auto-selects AppiumPythonAdapter."""
    from adapters.appium_python.facade import AppiumHealerFacade
    from xpath_healer.store.memory_repository import InMemoryMetadataRepository

    facade = AppiumHealerFacade(repository=InMemoryMetadataRepository())
    assert facade.adapter.__class__.__name__ == "AppiumPythonAdapter"


# ===========================================================================
# 7) Postgres workflow run repo — asyncpg fully mocked
# ===========================================================================


class _FakePGConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.fetched: list[tuple[str, tuple[Any, ...]]] = []
        self._next_fetchrow: Any = None
        self._next_fetch: list[Any] = []

    def transaction(self):
        outer = self

        class _Tx:
            async def __aenter__(self_):
                return None

            async def __aexit__(self_, *a):
                return None

        return _Tx()

    async def execute(self, query: str, *args: Any) -> None:
        self.executed.append((query, args))

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.fetched.append((query, args))
        return self._next_fetchrow

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.fetched.append((query, args))
        return list(self._next_fetch)


class _FakePGPool:
    def __init__(self, conn: _FakePGConn) -> None:
        self.conn = conn

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_):
                return pool.conn

            async def __aexit__(self_, *a):
                return None

        return _Ctx()

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_pg_workflow_run_repo_record_step_runs_insert_and_prune() -> None:
    from xpath_healer.store.workflow_run_pg_repository import PostgresWorkflowRunRepository

    repo = PostgresWorkflowRunRepository(
        dsn="postgres://fake", max_steps_per_workflow=10
    )
    conn = _FakePGConn()
    repo._pool = _FakePGPool(conn)

    await repo.record_step(
        StepRun(
            workflow_id="w",
            step_id="s1",
            status=STEP_STATUS_STEP_SUCCEEDED,
            locator_used={"kind": "xpath", "value": "//x"},
        )
    )
    assert len(conn.executed) == 2  # one INSERT, one DELETE prune
    insert_q, insert_args = conn.executed[0]
    assert "INSERT INTO xh_workflow_step_runs" in insert_q
    assert insert_args[0] == "w"  # workflow_id
    delete_q, delete_args = conn.executed[1]
    assert "DELETE FROM xh_workflow_step_runs" in delete_q
    assert delete_args == ("w", 10)


@pytest.mark.asyncio
async def test_pg_workflow_run_repo_update_step_status_returns_true_when_found() -> None:
    from xpath_healer.store.workflow_run_pg_repository import PostgresWorkflowRunRepository

    repo = PostgresWorkflowRunRepository(dsn="postgres://fake")
    conn = _FakePGConn()
    conn._next_fetchrow = {"id": 42}
    repo._pool = _FakePGPool(conn)

    updated = await repo.update_step_status(
        "w", "s1", STEP_STATUS_STEP_SUCCEEDED, note="ok"
    )
    assert updated is True
    # SELECT + UPDATE issued.
    assert len(conn.fetched) == 1
    assert len(conn.executed) == 1


@pytest.mark.asyncio
async def test_pg_workflow_run_repo_update_returns_false_when_no_heal_record() -> None:
    from xpath_healer.store.workflow_run_pg_repository import PostgresWorkflowRunRepository

    repo = PostgresWorkflowRunRepository(dsn="postgres://fake")
    conn = _FakePGConn()
    conn._next_fetchrow = None
    repo._pool = _FakePGPool(conn)

    updated = await repo.update_step_status(
        "w", "s1", STEP_STATUS_STEP_SUCCEEDED
    )
    assert updated is False
    assert len(conn.executed) == 0


@pytest.mark.asyncio
async def test_pg_workflow_run_repo_find_step_history_maps_rows() -> None:
    from xpath_healer.store.workflow_run_pg_repository import PostgresWorkflowRunRepository

    repo = PostgresWorkflowRunRepository(dsn="postgres://fake")
    conn = _FakePGConn()
    conn._next_fetch = [
        {
            "workflow_id": "w",
            "step_id": "s1",
            "status": STEP_STATUS_STEP_SUCCEEDED,
            "locator_used": {"kind": "xpath", "value": "//x"},
            "healer_stage": "rules",
            "page_signature": "abc",
            "duration_ms": 1.0,
            "failure_reason": "",
            "note": "ok",
            "recorded_at": None,
        }
    ]
    repo._pool = _FakePGPool(conn)
    history = await repo.find_step_history("w", "s1", limit=5)
    assert len(history) == 1
    assert history[0].status == STEP_STATUS_STEP_SUCCEEDED
    assert history[0].locator_used == {"kind": "xpath", "value": "//x"}
