"""Agentic workflow-rewrite proposal generator.

Mirrors the bounded-budget agent-loop pattern from
``xpath_healer/mcp/explorer.py`` — same ``LLMClient`` abstraction, same
budget-cap idea — but with workflow-level tools and a strict commit
schema (action ∈ ``{skip, abort}`` in the MVP).

Loop
----

1. Build a system + user prompt from the failed ``BuildInput`` (which
   carries ``workflow_context``) + the cascade failure summary.
2. Issue a chat turn with the available tools.
3. If the model called ``query_dom`` / ``inspect_matches``, dispatch via
   the same ``AutomationAdapter`` the test is using (works for both
   Selenium and Playwright callers).
4. If the model called ``commit_skip`` / ``commit_abort``, record the
   proposal and exit on the same turn (skip and abort are terminal).
5. Stop at ``max_rounds`` rounds or when the budget is exhausted.

Cost
----

Off by default (``stages.workflow_rewrite=False``). Bounded
defaults: 3 rounds, 6 tool calls, 1 proposal. Fires only when the
entire deterministic + MCP + RAG cascade returned ``failed`` for a
workflow step, so it's the true last resort.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import BuildInput, ElementMeta
from xpath_healer.core.workflow import (
    REWRITE_ACTION_ABORT,
    REWRITE_ACTION_INSERT_BEFORE,
    REWRITE_ACTION_REPLACE,
    REWRITE_ACTION_SKIP,
    WorkflowRewriteProposal,
    WorkflowStep,
    action_requires_new_step,
    is_supported_rewrite_action,
)
from xpath_healer.llm.client import (
    ChatMessage,
    LLMClient,
    ToolCall,
    ToolDefinition,
)
from xpath_healer.mcp.explorer import _exec_count, _exec_inspect


_SYSTEM_PROMPT = (
    "You are a workflow-rewrite assistant. The locator-healing cascade "
    "has failed to find the target element for the current step of a "
    "multi-step workflow. Use the tools to investigate what the page "
    "actually contains, then propose ONE of: \n"
    "  * commit_skip — the current step can be safely skipped (optional, "
    "    already-completed, or no longer required by the page state).\n"
    "  * commit_abort — the workflow cannot continue (mandatory step "
    "    has no equivalent UI on this page).\n"
    "  * commit_insert_before — a NEW prerequisite step must run first "
    "    (e.g. a CAPTCHA, a cookie banner accept, a Terms-of-Service "
    "    checkbox). Provide a fully-specified new_step the outer agent "
    "    can execute.\n"
    "  * commit_replace — the same intent is now realised by a different "
    "    UI mechanism (radio → dropdown, single field → typeahead). "
    "    Provide a fully-specified new_step.\n"
    "Do not invent locators — the cascade already tried that. Use tools "
    "to verify your hypothesis before committing. If you cannot decide "
    "with confidence, do not commit anything; the caller will fall back "
    "to a plain failure."
)


def _new_step_schema() -> dict[str, Any]:
    """Inline JSONSchema for a fully-specified replacement step.

    Mirrors :class:`WorkflowStep`'s field set so the model receives a
    clear contract when proposing insert_before / replace.
    """
    return {
        "type": "object",
        "properties": {
            "step_id": {"type": "string"},
            "intent": {"type": "string"},
            "action": {"type": "string"},
            "target_label": {"type": "string"},
            "target_kind": {"type": "string"},
            "expected_outcome": {"type": "string"},
            "optional": {"type": "boolean"},
        },
        "required": ["step_id", "intent", "action"],
        "additionalProperties": False,
    }


@dataclass(slots=True)
class RewriteResult:
    """What :meth:`WorkflowRewriter.rewrite` returns.

    ``proposal`` is ``None`` when no commit was made within budget.
    """

    proposal: WorkflowRewriteProposal | None = None
    rounds: int = 0
    tool_calls_made: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class WorkflowRewriter(Protocol):
    async def rewrite(
        self,
        adapter: AutomationAdapter,
        page: Any,
        inp: BuildInput,
        existing_meta: ElementMeta | None,
        cascade_error: str,
    ) -> RewriteResult:
        ...


def build_default_rewrite_tools() -> list[ToolDefinition]:
    """Tool set for the rewrite agent.

    Public so a custom rewriter can extend without redefining the
    schema. The MVP intentionally exposes only ``commit_skip`` and
    ``commit_abort`` (see ``core.workflow.is_mvp_rewrite_action``).
    """
    return [
        ToolDefinition(
            name="count_matches",
            description=(
                "Return how many elements the given xpath resolves to on "
                "the current page. Use to test hypotheses about whether "
                "an alternative element exists."
            ),
            parameters={
                "type": "object",
                "properties": {"xpath": {"type": "string"}},
                "required": ["xpath"],
                "additionalProperties": False,
            },
        ),
        ToolDefinition(
            name="inspect_matches",
            description=(
                "Inspect the first N elements matching xpath. Tag, "
                "stable attributes, short text, visibility, bounding box."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "xpath": {"type": "string"},
                    "max_items": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["xpath"],
                "additionalProperties": False,
            },
        ),
        ToolDefinition(
            name="commit_skip",
            description=(
                "Final answer: the current workflow step should be "
                "skipped. Use when the step is no longer present on the "
                "page (e.g. removed CAPTCHA, already-completed step)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["reason", "confidence"],
                "additionalProperties": False,
            },
        ),
        ToolDefinition(
            name="commit_abort",
            description=(
                "Final answer: the workflow cannot continue. Use when "
                "the step is mandatory and no equivalent UI exists on "
                "this page."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["reason", "confidence"],
                "additionalProperties": False,
            },
        ),
        ToolDefinition(
            name="commit_insert_before",
            description=(
                "Final answer: a new prerequisite step is required "
                "before the current step. Provide the new_step the "
                "outer agent should execute first."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "new_step": _new_step_schema(),
                },
                "required": ["reason", "confidence", "new_step"],
                "additionalProperties": False,
            },
        ),
        ToolDefinition(
            name="commit_replace",
            description=(
                "Final answer: the current step should be replaced by "
                "a different one (same intent, different UI mechanism). "
                "Provide the replacement new_step."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "new_step": _new_step_schema(),
                },
                "required": ["reason", "confidence", "new_step"],
                "additionalProperties": False,
            },
        ),
    ]


_COMMIT_TOOL_TO_ACTION = {
    "commit_skip": REWRITE_ACTION_SKIP,
    "commit_abort": REWRITE_ACTION_ABORT,
    "commit_insert_before": REWRITE_ACTION_INSERT_BEFORE,
    "commit_replace": REWRITE_ACTION_REPLACE,
}


class AgenticWorkflowRewriter(WorkflowRewriter):
    """Default agent-loop rewriter."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        max_rounds: int = 3,
        max_tool_calls: int = 6,
        tools: list[ToolDefinition] | None = None,
    ) -> None:
        self.llm = llm
        self.max_rounds = max(1, int(max_rounds))
        self.max_tool_calls = max(1, int(max_tool_calls))
        self.tools = tools if tools is not None else build_default_rewrite_tools()
        self._tool_names = {t.name for t in self.tools}
        self.logger = logging.getLogger("xpath_healer.workflow.rewriter")

    async def rewrite(
        self,
        adapter: AutomationAdapter,
        page: Any,
        inp: BuildInput,
        existing_meta: ElementMeta | None,
        cascade_error: str,
    ) -> RewriteResult:
        user_prompt = self._build_user_prompt(inp, existing_meta, cascade_error)
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt),
        ]
        proposal: WorkflowRewriteProposal | None = None
        tool_calls_made = 0
        rounds = 0

        while rounds < self.max_rounds and tool_calls_made < self.max_tool_calls:
            rounds += 1
            try:
                response = await self.llm.chat(messages, tools=self.tools)
            except Exception:
                self.logger.exception("Workflow rewriter LLM call failed")
                break

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=list(response.tool_calls),
                )
            )

            if not response.tool_calls:
                # Model declined to commit — let the caller fall back.
                break

            terminate = False
            for call in response.tool_calls:
                tool_calls_made += 1
                if tool_calls_made > self.max_tool_calls:
                    terminate = True
                    break

                if call.name in _COMMIT_TOOL_TO_ACTION:
                    action = _COMMIT_TOOL_TO_ACTION[call.name]
                    if not is_supported_rewrite_action(action):
                        messages.append(
                            ChatMessage(
                                role="tool",
                                tool_call_id=call.id,
                                content=json.dumps({"error": f"unsupported_action:{action}"}),
                            )
                        )
                        continue
                    args = call.arguments or {}
                    new_step_obj: WorkflowStep | None = None
                    if action_requires_new_step(action):
                        new_step_raw = args.get("new_step")
                        if not isinstance(new_step_raw, dict):
                            # Reject the commit and let the model retry
                            # with a properly-shaped new_step.
                            messages.append(
                                ChatMessage(
                                    role="tool",
                                    tool_call_id=call.id,
                                    content=json.dumps(
                                        {"error": "missing_new_step", "action": action}
                                    ),
                                )
                            )
                            continue
                        try:
                            new_step_obj = WorkflowStep.from_dict(new_step_raw)
                        except Exception as exc:
                            messages.append(
                                ChatMessage(
                                    role="tool",
                                    tool_call_id=call.id,
                                    content=json.dumps(
                                        {"error": "invalid_new_step", "detail": str(exc)}
                                    ),
                                )
                            )
                            continue
                        # Sanity check: required fields non-empty.
                        if not new_step_obj.step_id or not new_step_obj.intent or not new_step_obj.action:
                            messages.append(
                                ChatMessage(
                                    role="tool",
                                    tool_call_id=call.id,
                                    content=json.dumps(
                                        {"error": "incomplete_new_step"}
                                    ),
                                )
                            )
                            continue
                    proposal = WorkflowRewriteProposal(
                        action=action,
                        reason=str(args.get("reason") or ""),
                        confidence=float(args.get("confidence") or 0.0),
                        new_step=new_step_obj,
                        metadata={
                            "rounds": rounds,
                            "tool_calls": tool_calls_made,
                            "source": "agentic_workflow_rewriter",
                        },
                    )
                    messages.append(
                        ChatMessage(
                            role="tool",
                            tool_call_id=call.id,
                            content="ack",
                        )
                    )
                    terminate = True
                    break

                if call.name in self._tool_names:
                    payload = await self._dispatch_tool(adapter, page, call)
                    messages.append(
                        ChatMessage(
                            role="tool",
                            tool_call_id=call.id,
                            content=json.dumps(payload, ensure_ascii=True, default=str),
                        )
                    )
                    continue

                # Unknown tool — tell the model so it can recover.
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=json.dumps({"error": f"unknown_tool:{call.name}"}),
                    )
                )

            if terminate:
                break

        return RewriteResult(
            proposal=proposal,
            rounds=rounds,
            tool_calls_made=tool_calls_made,
            metadata={
                "committed": proposal is not None,
            },
        )

    async def _dispatch_tool(
        self,
        adapter: AutomationAdapter,
        page: Any,
        call: ToolCall,
    ) -> dict[str, Any]:
        """Reuse the MCP explorer's DOM-query primitives — identical
        semantics for adapter-agnostic ``count`` / ``inspect``."""
        args = call.arguments or {}
        try:
            if call.name == "count_matches":
                return await _exec_count(adapter, page, str(args.get("xpath") or ""))
            if call.name == "inspect_matches":
                return await _exec_inspect(
                    adapter,
                    page,
                    str(args.get("xpath") or ""),
                    int(args.get("max_items") or 3),
                )
        except Exception as exc:
            return {"error": "tool_dispatch_failed", "detail": str(exc)}
        return {"error": "unrecognized_tool", "name": call.name}

    @staticmethod
    def _build_user_prompt(
        inp: BuildInput,
        meta: ElementMeta | None,
        cascade_error: str,
    ) -> str:
        wf = getattr(inp, "workflow_context", None)
        wf_payload: dict[str, Any] | None = None
        if wf is not None and hasattr(wf, "current_step"):
            wf_payload = {
                "workflow_id": getattr(wf, "workflow_id", ""),
                "workflow_intent": getattr(wf, "workflow_intent", ""),
                "current_step": wf.current_step.to_dict() if hasattr(wf.current_step, "to_dict") else None,
                "prior_steps": [
                    s.to_dict() for s in getattr(wf, "prior_steps", []) if hasattr(s, "to_dict")
                ],
                "next_step_hint": (
                    wf.next_step_hint.to_dict()
                    if getattr(wf, "next_step_hint", None) is not None
                    and hasattr(wf.next_step_hint, "to_dict")
                    else None
                ),
            }
        prior: dict[str, Any] | None = None
        if meta is not None and getattr(meta, "signature", None) is not None:
            sig = meta.signature
            prior = {
                "tag": sig.tag,
                "stable_attrs": dict(sig.stable_attrs or {}),
                "short_text": sig.short_text,
            }
        payload = {
            "intent": {
                "label": getattr(inp.intent, "label", None) if inp.intent else None,
                "field_type": inp.field_type,
                "element_name": inp.element_name,
            },
            "workflow": wf_payload,
            "prior_memory": prior,
            "cascade_error": cascade_error,
        }
        return (
            "Decide whether to SKIP or ABORT the current workflow step. "
            "Use tools to inspect the page before committing.\n\n"
            + json.dumps(payload, ensure_ascii=True, default=str)
        )
