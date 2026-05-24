"""Phase 4a — WorkflowContext model, BuildInput plumbing, MCP prompt
enrichment, recover_workflow_step facade method, and the locator-only
misuse warning.

No Phase 4a code touches the deterministic cascade behaviour for
locator-only callers, so the entire existing test suite must continue
to pass alongside these additions.
"""

from __future__ import annotations

import json
import logging

import pytest

from xpath_healer.api.base import BaseHealerFacade
from xpath_healer.core.models import BuildInput, ElementMeta, Intent, LocatorSpec
from xpath_healer.core.workflow import (
    WORKFLOW_SHAPED_VAR_KEYS,
    StepOutcome,
    WorkflowContext,
    WorkflowStep,
)
from xpath_healer.llm.client import ChatMessage, ChatResponse, LLMClient, ToolCall, ToolDefinition
from xpath_healer.mcp import AgenticMCPExplorer


# ---------------------------------------------------------------------------
# Model round-trip
# ---------------------------------------------------------------------------


def test_workflow_step_round_trip() -> None:
    step = WorkflowStep(
        step_id="select-country",
        intent="pick country",
        action="select",
        target_label="Country",
        target_kind="dropdown",
        expected_outcome="country=US",
    )
    revived = WorkflowStep.from_dict(step.to_dict())
    assert revived == step


def test_step_outcome_round_trip() -> None:
    o = StepOutcome(step_id="s1", status="success", locator_used="//*[@id='x']", note="ok")
    assert StepOutcome.from_dict(o.to_dict()) == o


def test_workflow_context_round_trip() -> None:
    ctx = WorkflowContext(
        workflow_id="signup",
        workflow_intent="create a paying user",
        current_step=WorkflowStep(step_id="s2", intent="i", action="fill", target_label="Email"),
        prior_steps=[StepOutcome(step_id="s1", status="success", locator_used="//x")],
        next_step_hint=WorkflowStep(step_id="s3", intent="pwd", action="fill", target_label="Password"),
        metadata={"locale": "en-US"},
    )
    revived = WorkflowContext.from_dict(ctx.to_dict())
    assert revived.workflow_id == ctx.workflow_id
    assert revived.current_step == ctx.current_step
    assert revived.prior_steps == ctx.prior_steps
    assert revived.next_step_hint == ctx.next_step_hint
    assert revived.metadata == ctx.metadata


# ---------------------------------------------------------------------------
# BuildInput backward compat
# ---------------------------------------------------------------------------


def test_build_input_defaults_workflow_context_to_none() -> None:
    inp = BuildInput(
        page=None,
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
    )
    assert inp.workflow_context is None


def test_build_input_accepts_workflow_context() -> None:
    ctx = WorkflowContext(
        workflow_id="w",
        workflow_intent="i",
        current_step=WorkflowStep(step_id="s1", intent="i", action="fill"),
    )
    inp = BuildInput(
        page=None,
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        workflow_context=ctx,
    )
    assert inp.workflow_context is ctx


# ---------------------------------------------------------------------------
# MCP explorer prompt enrichment
# ---------------------------------------------------------------------------


class _RecordingLLM(LLMClient):
    """Captures the messages sent on each chat call."""

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


@pytest.mark.asyncio
async def test_mcp_prompt_omits_workflow_when_context_absent() -> None:
    llm = _RecordingLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_locator",
                        arguments={"xpath": "//x", "confidence": 0.9},
                    )
                ]
            )
        ]
    )
    explorer = AgenticMCPExplorer(llm)
    inp = BuildInput(
        page=None,
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        intent=Intent(label="Email"),
    )
    await explorer.explore(_NoopAdapter(), object(), inp, None)
    user_msg_content = llm.calls[0][1].content
    # Workflow key present but null when no context provided.
    assert '"workflow":null' in user_msg_content.replace(" ", "")
    # Prompt intro does not mention multi-step healing.
    assert "multi-step workflow" not in user_msg_content


@pytest.mark.asyncio
async def test_mcp_prompt_includes_workflow_when_context_present() -> None:
    llm = _RecordingLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_locator",
                        arguments={"xpath": "//x", "confidence": 0.9},
                    )
                ]
            )
        ]
    )
    explorer = AgenticMCPExplorer(llm)
    ctx = WorkflowContext(
        workflow_id="signup",
        workflow_intent="create paying user",
        current_step=WorkflowStep(
            step_id="s2",
            intent="email entry",
            action="fill",
            target_label="Email",
            target_kind="textbox",
            expected_outcome="email-filled",
        ),
        prior_steps=[StepOutcome(step_id="s1", status="success", locator_used="//*[@id='name']")],
        next_step_hint=WorkflowStep(step_id="s3", intent="password", action="fill", target_label="Password"),
    )
    inp = BuildInput(
        page=None,
        app_id="a",
        page_name="signup",
        element_name="email_input",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        intent=Intent(label="Email"),
        workflow_context=ctx,
    )
    await explorer.explore(_NoopAdapter(), object(), inp, None)
    content = llm.calls[0][1].content
    assert "multi-step workflow" in content
    payload_json = content.split("\n\n", 1)[1]
    payload = json.loads(payload_json)
    assert payload["workflow"]["workflow_id"] == "signup"
    assert payload["workflow"]["current_step"]["target_label"] == "Email"
    assert payload["workflow"]["prior_steps"][0]["locator_used"] == "//*[@id='name']"
    assert payload["workflow"]["next_step_hint"]["target_label"] == "Password"


# ---------------------------------------------------------------------------
# recover_workflow_step facade method
# ---------------------------------------------------------------------------


class _StubFacade(BaseHealerFacade):
    """Minimal subclass that intercepts the healing_service call so we
    can inspect the BuildInput that reached it."""

    def __init__(self) -> None:
        # Skip BaseHealerFacade.__init__ to keep the test hermetic — we
        # only need recover_locator / recover_workflow_step + the logger.
        self.logger = logging.getLogger("test.stub_facade")
        self.captured: list[BuildInput] = []

        class _FakeHealing:
            def __init__(self, captured: list[BuildInput]) -> None:
                self._captured = captured

            async def recover_locator(self, ctx, build_input):
                self._captured.append(build_input)
                from xpath_healer.core.models import Recovered

                return Recovered(status="success", correlation_id="cid")

        self.healing_service = _FakeHealing(self.captured)
        self.ctx = None  # not exercised here


@pytest.mark.asyncio
async def test_recover_workflow_step_threads_context_into_build_input() -> None:
    facade = _StubFacade()
    wf = WorkflowContext(
        workflow_id="w",
        workflow_intent="i",
        current_step=WorkflowStep(
            step_id="s1",
            intent="fill",
            action="fill",
            target_label="Username",
        ),
    )
    rec = await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=wf,
    )
    assert rec.status == "success"
    assert len(facade.captured) == 1
    inp = facade.captured[0]
    assert inp.workflow_context is wf
    # Auto-derived label from current_step.target_label since vars["label"]
    # was not provided.
    assert inp.intent.label == "Username"


@pytest.mark.asyncio
async def test_recover_workflow_step_rejects_missing_context() -> None:
    facade = _StubFacade()
    with pytest.raises(ValueError):
        await facade.recover_workflow_step(
            page=object(),
            app_id="a",
            page_name="p",
            element_name="e",
            field_type="textbox",
            fallback=LocatorSpec(kind="css", value="*"),
            vars={},
            workflow_context=None,
        )


@pytest.mark.asyncio
async def test_recover_workflow_step_rejects_wrong_context_type() -> None:
    facade = _StubFacade()
    with pytest.raises(TypeError):
        await facade.recover_workflow_step(
            page=object(),
            app_id="a",
            page_name="p",
            element_name="e",
            field_type="textbox",
            fallback=LocatorSpec(kind="css", value="*"),
            vars={},
            workflow_context={"not": "a WorkflowContext"},
        )


@pytest.mark.asyncio
async def test_recover_locator_sets_workflow_context_none_explicitly() -> None:
    facade = _StubFacade()
    await facade.recover_locator(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={"label": "Email"},
    )
    assert facade.captured[0].workflow_context is None


# ---------------------------------------------------------------------------
# Misuse warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recover_locator_warns_when_vars_contain_workflow_shaped_keys(
    caplog: pytest.LogCaptureFixture,
) -> None:
    facade = _StubFacade()
    caplog.set_level(logging.WARNING, logger="test.stub_facade")
    await facade.recover_locator(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={"workflow_id": "signup", "label": "Email"},
    )
    messages = " ".join(rec.getMessage() for rec in caplog.records)
    assert "workflow-shaped vars" in messages
    assert "workflow_id" in messages


@pytest.mark.asyncio
async def test_recover_locator_does_not_warn_on_plain_vars(
    caplog: pytest.LogCaptureFixture,
) -> None:
    facade = _StubFacade()
    caplog.set_level(logging.WARNING, logger="test.stub_facade")
    await facade.recover_locator(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={"label": "Email", "data-testid": "email-input"},
    )
    messages = " ".join(rec.getMessage() for rec in caplog.records)
    assert "workflow-shaped vars" not in messages


def test_workflow_shaped_keys_inventory_is_non_empty() -> None:
    # Guard against accidental wipe of the inventory — the warning
    # depends on it.
    assert "workflow_id" in WORKFLOW_SHAPED_VAR_KEYS
    assert "step_id" in WORKFLOW_SHAPED_VAR_KEYS
