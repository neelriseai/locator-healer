"""Phase 4c — workflow rewrite agent + facade post-cascade integration."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from xpath_healer.api.base import BaseHealerFacade
from xpath_healer.core.models import BuildInput, Intent, LocatorSpec, Recovered
from xpath_healer.core.workflow import (
    REWRITE_ACTION_ABORT,
    REWRITE_ACTION_SKIP,
    WorkflowContext,
    WorkflowRewriteProposal,
    WorkflowStep,
    is_mvp_rewrite_action,
)
from xpath_healer.llm.client import ChatMessage, ChatResponse, LLMClient, ToolCall, ToolDefinition
from xpath_healer.workflow import AgenticWorkflowRewriter


# ---------------------------------------------------------------------------
# Scripted LLM + minimal adapter
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Data-model + helpers
# ---------------------------------------------------------------------------


def test_workflow_rewrite_proposal_round_trip() -> None:
    p = WorkflowRewriteProposal(
        action=REWRITE_ACTION_SKIP,
        reason="captcha removed",
        confidence=0.82,
        metadata={"source": "test"},
    )
    revived = WorkflowRewriteProposal.from_dict(p.to_dict())
    assert revived.action == p.action
    assert revived.reason == p.reason
    assert revived.confidence == p.confidence
    assert revived.new_step is None
    assert revived.metadata == p.metadata


def test_is_mvp_rewrite_action_accepts_all_supported_actions() -> None:
    # Phase 5 broadened the supported set to include insert_before / replace.
    # is_mvp_rewrite_action is now a back-compat alias for
    # is_supported_rewrite_action.
    assert is_mvp_rewrite_action(REWRITE_ACTION_SKIP)
    assert is_mvp_rewrite_action(REWRITE_ACTION_ABORT)
    assert is_mvp_rewrite_action("insert_before")
    assert is_mvp_rewrite_action("replace")
    assert not is_mvp_rewrite_action("")
    assert not is_mvp_rewrite_action("nope")


def test_recovered_to_dict_emits_rewrite_proposal_when_present() -> None:
    rec = Recovered(
        status="failed",
        correlation_id="c",
        rewrite_proposal=WorkflowRewriteProposal(
            action=REWRITE_ACTION_SKIP, reason="r", confidence=0.9
        ),
    )
    d = rec.to_dict()
    assert d["rewrite_proposal"]["action"] == REWRITE_ACTION_SKIP
    assert d["rewrite_proposal"]["confidence"] == 0.9


def test_recovered_to_dict_emits_null_rewrite_proposal_when_absent() -> None:
    rec = Recovered(status="success", correlation_id="c")
    assert rec.to_dict()["rewrite_proposal"] is None


# ---------------------------------------------------------------------------
# Agent loop — direct tests
# ---------------------------------------------------------------------------


def _wf_inp(label: str = "Email") -> BuildInput:
    return BuildInput(
        page=object(),
        app_id="a",
        page_name="signup",
        element_name="email_input",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        intent=Intent(label=label),
        workflow_context=WorkflowContext(
            workflow_id="signup",
            workflow_intent="create user",
            current_step=WorkflowStep(
                step_id="fill_email",
                intent="email entry",
                action="fill",
                target_label=label,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_rewriter_commits_skip_proposal() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_skip",
                        arguments={"reason": "captcha was removed", "confidence": 0.85},
                    )
                ]
            )
        ]
    )
    rewriter = AgenticWorkflowRewriter(llm)
    result = await rewriter.rewrite(
        _NoopAdapter(), object(), _wf_inp(), None, cascade_error="not found"
    )
    assert result.proposal is not None
    assert result.proposal.action == REWRITE_ACTION_SKIP
    assert result.proposal.reason == "captcha was removed"
    assert result.proposal.confidence == 0.85
    assert result.proposal.metadata["source"] == "agentic_workflow_rewriter"
    assert result.rounds == 1


@pytest.mark.asyncio
async def test_rewriter_commits_abort_proposal() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_abort",
                        arguments={"reason": "no submit form", "confidence": 0.92},
                    )
                ]
            )
        ]
    )
    rewriter = AgenticWorkflowRewriter(llm)
    result = await rewriter.rewrite(
        _NoopAdapter(), object(), _wf_inp(), None, cascade_error="not found"
    )
    assert result.proposal is not None
    assert result.proposal.action == REWRITE_ACTION_ABORT


@pytest.mark.asyncio
async def test_rewriter_uses_count_then_commits() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(id="t1", name="count_matches", arguments={"xpath": "//foo"})
                ]
            ),
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_skip",
                        arguments={"reason": "page has no captcha", "confidence": 0.7},
                    )
                ]
            ),
        ]
    )
    rewriter = AgenticWorkflowRewriter(llm)
    result = await rewriter.rewrite(
        _NoopAdapter(), object(), _wf_inp(), None, cascade_error=""
    )
    assert result.rounds == 2
    assert result.tool_calls_made == 2
    assert result.proposal is not None
    assert result.proposal.action == REWRITE_ACTION_SKIP


@pytest.mark.asyncio
async def test_rewriter_no_commit_returns_none_proposal() -> None:
    llm = _ScriptedLLM([ChatResponse(content="I am unsure", tool_calls=[])])
    rewriter = AgenticWorkflowRewriter(llm)
    result = await rewriter.rewrite(
        _NoopAdapter(), object(), _wf_inp(), None, cascade_error=""
    )
    assert result.proposal is None
    assert result.rounds == 1


@pytest.mark.asyncio
async def test_rewriter_max_rounds_budget_caps_loop() -> None:
    looping = ChatResponse(
        tool_calls=[ToolCall(id="t", name="count_matches", arguments={"xpath": "//foo"})]
    )
    llm = _ScriptedLLM([looping] * 10)
    rewriter = AgenticWorkflowRewriter(llm, max_rounds=2, max_tool_calls=100)
    result = await rewriter.rewrite(
        _NoopAdapter(), object(), _wf_inp(), None, cascade_error=""
    )
    assert result.rounds == 2
    assert result.proposal is None


@pytest.mark.asyncio
async def test_rewriter_unknown_tool_does_not_break_loop() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="t1", name="hallucinated", arguments={})]
            ),
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_skip",
                        arguments={"reason": "recovered", "confidence": 0.6},
                    )
                ]
            ),
        ]
    )
    rewriter = AgenticWorkflowRewriter(llm)
    result = await rewriter.rewrite(
        _NoopAdapter(), object(), _wf_inp(), None, cascade_error=""
    )
    assert result.proposal is not None
    assert result.proposal.action == REWRITE_ACTION_SKIP


@pytest.mark.asyncio
async def test_rewriter_prompt_includes_workflow_and_cascade_error() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_abort",
                        arguments={"reason": "x", "confidence": 0.9},
                    )
                ]
            )
        ]
    )
    rewriter = AgenticWorkflowRewriter(llm)
    await rewriter.rewrite(
        _NoopAdapter(),
        object(),
        _wf_inp(),
        None,
        cascade_error="all stages exhausted",
    )
    user_msg = llm.calls[0][1]
    assert user_msg.role == "user"
    assert "workflow" in user_msg.content
    assert "all stages exhausted" in user_msg.content


# ---------------------------------------------------------------------------
# Facade integration — attach proposal after failed cascade
# ---------------------------------------------------------------------------


class _StubRewriter:
    """Returns a pre-built proposal regardless of input."""

    def __init__(self, proposal: WorkflowRewriteProposal | None) -> None:
        self._proposal = proposal
        self.calls: int = 0

    async def rewrite(self, adapter, page, inp, existing_meta, cascade_error):
        self.calls += 1

        class _R:
            def __init__(self, p):
                self.proposal = p
                self.rounds = 1
                self.tool_calls_made = 1
                self.metadata: dict[str, Any] = {}

        return _R(self._proposal)


class _BoomRewriter:
    async def rewrite(self, *a, **kw):
        raise RuntimeError("LLM down")


class _StubFacade(BaseHealerFacade):
    """Bypasses BaseHealerFacade.__init__; lets us drive the
    post-cascade rewrite hook in isolation."""

    def __init__(
        self,
        *,
        recovered: Recovered,
        rewriter: object | None,
    ) -> None:
        self.logger = logging.getLogger("test.rewriter_facade")
        self.adapter = _NoopAdapter()
        self.workflow_run_repository = None
        self.workflow_rewriter = rewriter
        self.ctx = None

        class _FakeHealing:
            def __init__(self, recovered: Recovered) -> None:
                self._recovered = recovered

            async def recover_locator(self, ctx, build_input):
                return self._recovered

        self.healing_service = _FakeHealing(recovered)


def _wf_context() -> WorkflowContext:
    return WorkflowContext(
        workflow_id="signup",
        workflow_intent="create user",
        current_step=WorkflowStep(
            step_id="fill_email",
            intent="email entry",
            action="fill",
            target_label="Email",
        ),
    )


@pytest.mark.asyncio
async def test_recover_workflow_step_attaches_rewrite_proposal_on_failure() -> None:
    stub = _StubRewriter(
        WorkflowRewriteProposal(
            action=REWRITE_ACTION_SKIP, reason="captcha gone", confidence=0.8
        )
    )
    facade = _StubFacade(
        recovered=Recovered(status="failed", correlation_id="c", error="all stages failed"),
        rewriter=stub,
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
    )
    assert stub.calls == 1
    assert out.rewrite_proposal is not None
    assert out.rewrite_proposal.action == REWRITE_ACTION_SKIP
    assert out.rewrite_proposal.reason == "captcha gone"
    # Status is NOT mutated by the rewriter.
    assert out.status == "failed"


@pytest.mark.asyncio
async def test_recover_workflow_step_does_not_invoke_rewriter_on_success() -> None:
    stub = _StubRewriter(WorkflowRewriteProposal(action=REWRITE_ACTION_SKIP))
    facade = _StubFacade(
        recovered=Recovered(
            status="success",
            correlation_id="c",
            locator_spec=LocatorSpec(kind="xpath", value="//x"),
        ),
        rewriter=stub,
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
    )
    assert stub.calls == 0
    assert out.rewrite_proposal is None


@pytest.mark.asyncio
async def test_recover_workflow_step_no_rewriter_yields_none_proposal() -> None:
    facade = _StubFacade(
        recovered=Recovered(status="failed", correlation_id="c"),
        rewriter=None,
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
    )
    assert out.rewrite_proposal is None
    assert out.status == "failed"


@pytest.mark.asyncio
async def test_recover_workflow_step_swallows_rewriter_exceptions() -> None:
    facade = _StubFacade(
        recovered=Recovered(status="failed", correlation_id="c"),
        rewriter=_BoomRewriter(),
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
    )
    assert out.rewrite_proposal is None
    assert out.status == "failed"


@pytest.mark.asyncio
async def test_recover_workflow_step_rewriter_returning_none_proposal_is_no_op() -> None:
    facade = _StubFacade(
        recovered=Recovered(status="failed", correlation_id="c"),
        rewriter=_StubRewriter(proposal=None),
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
    )
    assert out.rewrite_proposal is None
