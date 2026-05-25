"""Agentic exploratory healer.

Loop sketch
-----------
1. Build a system + user prompt from ``BuildInput`` (intent, field type,
   anchor, prior memory if any).
2. Issue a chat turn with the available tools.
3. If the model returned tool calls, execute each via the adapter and
   append the results as tool messages, then iterate.
4. If the model called ``commit_locator(xpath, reason, confidence)`` —
   collect that locator, optionally continue if the budget allows for
   more proposals, and return all commits ranked by confidence.
5. Stop at ``max_rounds`` rounds or when no further tool calls are
   produced, whichever comes first. Returns an empty result on
   exhaustion so the caller falls through to the RAG stage.

Tools
-----
``count_matches(xpath)``
    How many elements the xpath resolves to right now.

``inspect_matches(xpath, max_items=3)``
    Tag, attrs, short text, visibility, bbox of the first N matches.

``commit_locator(xpath, reason, confidence)``
    Final answer. The model can commit one or more — the healer ranks by
    ``confidence`` and the validator decides the winner.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import (
    BuildInput,
    ElementMeta,
    LocatorSpec,
)
from xpath_healer.llm.client import (
    ChatMessage,
    LLMClient,
    ToolCall,
    ToolDefinition,
)


_SYSTEM_PROMPT = (
    "You are a precision locator-finder. Use the provided tools to find "
    "ONE robust XPath that resolves to exactly the intended element on "
    "the current page.\n\n"
    "RECOMMENDED FLOW for an unfamiliar page (cheap + accurate):\n"
    "  1. Call read_page_outline FIRST (optionally with "
    "focus_text=<the label/text from the intent>). One round-trip gives "
    "you the structural layout — far cheaper than guessing xpaths.\n"
    "  2. Form a hypothesis XPath grounded in the outline.\n"
    "  3. Validate with count_matches (must be 1) and inspect_matches.\n"
    "  4. commit_locator with your strongest candidate.\n\n"
    "DETERMINISTIC PLAYBOOK (the rules / page_index / option_fingerprint "
    "stages use these — reuse the same patterns to save rounds):\n"
    "  * label[@for]=input[@id]  — strongest when both sides are stable.\n"
    "      //input[@id = (//label[normalize-space()='Email']/@for)[1]]\n"
    "  * label-anchored bidirectional sibling — works when @for is "
    "missing. Try BOTH preceding and following axes from the label:\n"
    "      //label[normalize-space()='Country']/following::select[1]\n"
    "      //label[normalize-space()='Country']/preceding::select[1]\n"
    "  * container-scoped lookup — narrowest stable form-row ancestor "
    "(form / fieldset / li / tr / div with @role or @aria-label) limits "
    "the search and prevents false positives elsewhere on the page:\n"
    "      //form//label[normalize-space()='Email']/ancestor::*[self::li "
    "or self::div][1]//input[1]\n"
    "  * tree/expand patterns — for nested checkbox or accordion trees "
    "(rct-* / role='treeitem'), parent must be expanded before child "
    "nodes exist. Read the outline AFTER an expand action; the new "
    "subtree appears with its own toggle buttons.\n"
    "  * option / value fingerprinting — for selects, the option list "
    "(`option/@value`, option text) is more stable than the label.\n\n"
    "PRIORITY ORDER for attribute selection:\n"
    "  data-testid > id > name > role > aria-label > placeholder > "
    "type-only ; positional indexes [n] are the LAST resort.\n\n"
    "ANTI-PATTERNS to avoid:\n"
    "  * Inventing attributes you have not verified via count_matches.\n"
    "  * Long positional paths like /html/body/div[3]/div[2]/form/...\n"
    "  * Wrapping every guess in inspect_matches; one outline + one "
    "count_matches is usually enough.\n\n"
    "If you cannot find the element after a focused outline + a few "
    "probes, do not invent one — simply stop and the system will fall "
    "through to the next layer."
)


@dataclass(slots=True)
class ExplorationResult:
    """What an exploration returns.

    ``locators`` are ranked by ``score`` descending; the caller wraps
    each in a ``CandidateSpec`` for validation.
    """

    locators: list[LocatorSpec] = field(default_factory=list)
    rounds: int = 0
    tool_calls_made: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MCPExploratoryHealer(Protocol):
    """Protocol that any exploratory healer impl must satisfy."""

    async def explore(
        self,
        adapter: AutomationAdapter,
        page: Any,
        inp: BuildInput,
        existing_meta: ElementMeta | None,
    ) -> ExplorationResult:
        ...


def build_default_tools() -> list[ToolDefinition]:
    """Return the canonical agent tool set.

    Public so a custom explorer can extend (e.g. add ``click_element``
    for stateful pages) without re-deriving the schema.

    Ordering matters: ``read_page_outline`` comes first so the model
    naturally calls it once before guessing xpaths blindly. The
    bounded ``max_chars`` keeps a single outline call cheap (few KB
    of context) — much better than 5+ probe rounds for complex pages.
    """
    return [
        ToolDefinition(
            name="read_page_outline",
            description=(
                "Read a compact structural outline of the current page. "
                "Lists interactive + landmark elements (input, button, a, "
                "select, textarea, label, h1-h6, [role], [aria-label]) with "
                "tag, stable attributes, short text, indented by DOM depth. "
                "Use this FIRST on an unfamiliar page so subsequent "
                "count_matches / inspect_matches calls can be targeted "
                "instead of guessed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "max_chars": {
                        "type": "integer",
                        "minimum": 500,
                        "maximum": 24000,
                        "description": "Truncate output at this many chars (default 8000).",
                    },
                    "focus_text": {
                        "type": "string",
                        "description": (
                            "If set, only include nodes whose text/aria-label "
                            "contains this substring OR are within 6 DOM "
                            "levels of such a node. Sharpens the outline "
                            "when you already have a target label."
                        ),
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        ),
        ToolDefinition(
            name="count_matches",
            description=(
                "Return how many elements the given xpath resolves to on "
                "the current page. Use this to validate uniqueness before "
                "committing."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "xpath": {"type": "string", "description": "XPath expression"},
                },
                "required": ["xpath"],
                "additionalProperties": False,
            },
        ),
        ToolDefinition(
            name="inspect_matches",
            description=(
                "Inspect the first N elements matching xpath. Returns tag, "
                "stable attributes, short text, visibility and bounding box. "
                "Use to verify an xpath resolves to the right element."
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
            name="commit_locator",
            description=(
                "Final answer. Submit an xpath you are confident resolves "
                "to exactly the intended element. You may submit multiple "
                "candidates; rank by confidence."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "xpath": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["xpath", "confidence"],
                "additionalProperties": False,
            },
        ),
    ]


class AgenticMCPExplorer(MCPExploratoryHealer):
    """Default agent-loop implementation.

    Configurable budget bounds:

    * ``max_rounds``       — at most N chat turns
    * ``max_tool_calls``   — at most N tool calls across the whole loop
    * ``max_commit_count`` — stop after this many ``commit_locator`` calls
    """

    def __init__(
        self,
        llm: LLMClient,
        *,
        max_rounds: int = 5,
        max_tool_calls: int = 12,
        max_commit_count: int = 3,
        tools: list[ToolDefinition] | None = None,
    ) -> None:
        self.llm = llm
        self.max_rounds = max(1, int(max_rounds))
        self.max_tool_calls = max(1, int(max_tool_calls))
        self.max_commit_count = max(1, int(max_commit_count))
        self.tools = tools if tools is not None else build_default_tools()
        self._tool_names = {t.name for t in self.tools}
        self.logger = logging.getLogger("xpath_healer.mcp.explorer")

    async def explore(
        self,
        adapter: AutomationAdapter,
        page: Any,
        inp: BuildInput,
        existing_meta: ElementMeta | None,
    ) -> ExplorationResult:
        user_prompt = self._build_user_prompt(inp, existing_meta)
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt),
        ]
        commits: list[dict[str, Any]] = []
        tool_calls_made = 0
        rounds = 0

        while rounds < self.max_rounds and tool_calls_made < self.max_tool_calls:
            rounds += 1
            try:
                response = await self.llm.chat(messages, tools=self.tools)
            except Exception:
                self.logger.exception("MCP explorer LLM call failed")
                break

            # Persist the assistant turn (with any tool_calls) so the
            # next round's chat history is well-formed for the provider.
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=list(response.tool_calls),
                )
            )

            if not response.tool_calls:
                # Model wrote prose with no tool call → nothing more to do.
                break

            stop_early = False
            commits_this_turn = 0
            non_commits_this_turn = 0
            for call in response.tool_calls:
                tool_calls_made += 1
                if tool_calls_made > self.max_tool_calls:
                    stop_early = True
                    break

                if call.name == "commit_locator":
                    commit = self._record_commit(call.arguments)
                    if commit:
                        commits.append(commit)
                        commits_this_turn += 1
                    messages.append(
                        ChatMessage(
                            role="tool",
                            tool_call_id=call.id,
                            content="ack",
                        )
                    )
                    if len(commits) >= self.max_commit_count:
                        stop_early = True
                        break
                    continue

                if call.name in self._tool_names:
                    non_commits_this_turn += 1
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
                non_commits_this_turn += 1
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=json.dumps({"error": f"unknown_tool:{call.name}"}),
                    )
                )

            # A turn that produced only commits (no investigative tool
            # calls) means the model has decided — there is nothing to
            # gain from another round. Exit immediately so we don't burn
            # budget on a silent follow-up turn.
            if commits_this_turn > 0 and non_commits_this_turn == 0:
                break

            if stop_early:
                break

        # Rank commits by confidence (high → low).
        commits.sort(key=lambda c: float(c.get("confidence") or 0.0), reverse=True)
        locators: list[LocatorSpec] = []
        for c in commits:
            xpath = str(c.get("xpath") or "").strip()
            if not xpath:
                continue
            locators.append(
                LocatorSpec(
                    kind="xpath",
                    value=xpath,
                    options={
                        "_mcp_confidence": float(c.get("confidence") or 0.0),
                        "_mcp_reason": str(c.get("reason") or ""),
                    },
                )
            )
        return ExplorationResult(
            locators=locators,
            rounds=rounds,
            tool_calls_made=tool_calls_made,
            metadata={"commit_count": len(commits)},
        )

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def _dispatch_tool(
        self,
        adapter: AutomationAdapter,
        page: Any,
        call: ToolCall,
    ) -> dict[str, Any]:
        args = call.arguments or {}
        try:
            if call.name == "read_page_outline":
                max_chars_raw = args.get("max_chars")
                try:
                    max_chars = int(max_chars_raw) if max_chars_raw is not None else 8000
                except (TypeError, ValueError):
                    max_chars = 8000
                return await _exec_read_outline(
                    adapter,
                    page,
                    max_chars=max_chars,
                    focus_text=str(args.get("focus_text") or ""),
                )
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
    def _record_commit(args: dict[str, Any]) -> dict[str, Any] | None:
        xpath = str(args.get("xpath") or "").strip()
        if not xpath:
            return None
        return {
            "xpath": xpath,
            "reason": str(args.get("reason") or ""),
            "confidence": float(args.get("confidence") or 0.0),
        }

    @staticmethod
    def _build_user_prompt(inp: BuildInput, meta: ElementMeta | None) -> str:
        intent_payload: dict[str, Any] = {
            "app_id": inp.app_id,
            "page_name": inp.page_name,
            "element_name": inp.element_name,
            "field_type": inp.field_type,
            "label": (inp.intent.label if inp.intent else None),
            "text": (inp.intent.text if inp.intent else None),
            "vars": dict(inp.vars or {}),
        }
        if inp.fallback is not None:
            intent_payload["original_fallback"] = inp.fallback.to_dict()
        prior: dict[str, Any] | None = None
        if meta is not None and meta.signature is not None:
            sig = meta.signature
            prior = {
                "tag": sig.tag,
                "stable_attrs": dict(sig.stable_attrs or {}),
                "short_text": sig.short_text,
                "container_lca_path": list(sig.container_lca_path or []),
                "option_set": dict(sig.option_set or {}),
            }
        # Phase 4a — workflow-aware enrichment. Only included when the
        # caller went through ``recover_workflow_step`` so locator-only
        # callers see the same prompt as before.
        workflow_payload: dict[str, Any] | None = None
        wf = getattr(inp, "workflow_context", None)
        if wf is not None and hasattr(wf, "current_step"):
            workflow_payload = {
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
        payload = {
            "intent": intent_payload,
            "prior_memory": prior,
            "workflow": workflow_payload,
        }
        prompt_intro = (
            "Find an XPath for the element described below. Use tools to "
            "verify your guess before committing.\n\n"
        )
        if workflow_payload is not None:
            prompt_intro = (
                "You are healing one step of a multi-step workflow. The "
                "step's intent and the surrounding sequence are in the "
                "`workflow` section below — use them as context but "
                "find an XPath only for the CURRENT step's target. Use "
                "tools to verify before committing.\n\n"
            )
        return prompt_intro + json.dumps(payload, ensure_ascii=True, default=str)


# ---------------------------------------------------------------------------
# Page-side tool executors (single evaluate per call, adapter-agnostic).
# ---------------------------------------------------------------------------


async def _exec_count(adapter: AutomationAdapter, page: Any, xpath: str) -> dict[str, Any]:
    if not xpath:
        return {"count": 0, "error": "empty_xpath"}
    spec = LocatorSpec(kind="xpath", value=xpath)
    try:
        locator = await adapter.resolve_locator(page, spec)
        count = await locator.count()
    except Exception as exc:
        return {"count": 0, "error": "resolve_failed", "detail": str(exc)}
    return {"count": int(count or 0)}


_INSPECT_SCRIPT = """el => {
    const out = [];
    const items = [el];
    for (const node of items) {
        const attrs = {};
        for (const a of Array.from(node.attributes || [])) {
            attrs[a.name] = a.value;
        }
        let visible = false;
        if (node.getBoundingClientRect) {
            const r = node.getBoundingClientRect();
            visible = (r.width > 0 && r.height > 0);
        }
        out.push({
            tag: (node.tagName || "").toLowerCase(),
            attrs,
            text: ((node.innerText || node.textContent || "") + "").trim().slice(0, 120),
            visible,
            bbox: node.getBoundingClientRect ? (() => { const r = node.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })() : null,
        });
    }
    return out;
}"""


_PAGE_OUTLINE_SCRIPT = """(el, args) => {
    const maxChars = Math.max(500, Math.min(24000, (args && args.maxChars) || 8000));
    const focus = (args && args.focusText ? String(args.focusText) : "").trim().toLowerCase();
    // Helper — pull the best human-readable text for an element:
    // visible label > aria-label > placeholder > title > innerText.
    const humanText = (n) => {
        const aria = n.getAttribute && n.getAttribute('aria-label');
        if (aria && aria.trim()) return aria.trim().slice(0, 80);
        const ph = n.getAttribute && n.getAttribute('placeholder');
        if (ph && ph.trim()) return ph.trim().slice(0, 80);
        const title = n.getAttribute && n.getAttribute('title');
        if (title && title.trim()) return title.trim().slice(0, 80);
        const txt = ((n.innerText || n.textContent || '') + '').replace(/\\s+/g, ' ').trim();
        return txt ? txt.slice(0, 80) : '';
    };
    // We are called as a locator evaluate against the document root,
    // so `el` is the html element. Use document for traversal.
    const root = document.documentElement;
    // Interactive + structural tags. Anything else only appears if it
    // carries a role or aria-label.
    const interactiveTags = new Set([
        "input","textarea","select","button","a","label",
        "h1","h2","h3","h4","h5","h6","summary","option","fieldset",
    ]);
    const normalize = (s) => (s || "").toString().replace(/\\s+/g, " ").trim();
    const matchesFocus = (text) => {
        if (!focus) return false;
        return text.toLowerCase().includes(focus);
    };
    const stableAttrTokens = (n) => {
        const out = [];
        const grab = (k, alias) => {
            const v = n.getAttribute && n.getAttribute(k);
            if (v) out.push(`${alias || k}=${v}`);
        };
        grab("data-testid", "testid");
        grab("id");
        grab("name");
        grab("role");
        grab("type");
        grab("aria-label", "aria");
        grab("placeholder", "ph");
        grab("for");
        return out;
    };
    // First pass: collect every node we'd consider including.
    const collected = [];
    let depth = -1;
    const walk = (n, d) => {
        if (!n || n.nodeType !== 1) return;
        const tag = (n.tagName || "").toLowerCase();
        const role = n.getAttribute ? n.getAttribute("role") : null;
        const aria = n.getAttribute ? n.getAttribute("aria-label") : null;
        // Prefer human-friendly text so the decomposer reads it as the
        // visible label (aria-label > placeholder > title > innerText).
        const text = humanText(n);
        const isInteractive = interactiveTags.has(tag) || !!role || !!aria;
        if (isInteractive) {
            collected.push({n, d, tag, role, aria, text, attrs: stableAttrTokens(n)});
        }
        for (const c of n.children || []) walk(c, d + 1);
    };
    walk(root, 0);
    // Second pass: if focus is set, keep only entries that match OR are
    // within 6 DOM levels of a match (so structural ancestors surface).
    let visible = collected;
    if (focus) {
        const matchedDepths = collected
            .filter(c => matchesFocus(c.text) || matchesFocus(c.aria || ""))
            .map(c => c);
        const keep = new Set(matchedDepths);
        for (const m of matchedDepths) {
            // include parents up to 6 depths and direct descendants 6 deep
            let cur = m.n.parentElement;
            let up = 0;
            while (cur && up < 6) {
                const entry = collected.find(c => c.n === cur);
                if (entry) keep.add(entry);
                cur = cur.parentElement;
                up += 1;
            }
            // descendants
            const desc = m.n.querySelectorAll("*");
            for (const d of desc) {
                const entry = collected.find(c => c.n === d);
                if (entry) keep.add(entry);
            }
        }
        visible = collected.filter(c => keep.has(c));
    }
    // Render compact lines.
    const lines = [];
    let total = 0;
    for (const c of visible) {
        const attrPart = c.attrs.length ? "[" + c.attrs.join(",") + "]" : "";
        const textPart = c.text ? ` "${c.text}"` : "";
        const indent = "  ".repeat(Math.min(c.d, 12));
        const line = `${indent}${c.tag}${attrPart}${textPart}`;
        if (total + line.length + 1 > maxChars) {
            lines.push("... (truncated)");
            break;
        }
        lines.push(line);
        total += line.length + 1;
    }
    return {
        outline: lines.join("\\n"),
        total_nodes_considered: collected.length,
        total_nodes_emitted: lines.length,
        focus_text: focus,
    };
}"""


async def _exec_read_outline(
    adapter: AutomationAdapter,
    page: Any,
    *,
    max_chars: int,
    focus_text: str,
) -> dict[str, Any]:
    """Single-roundtrip structural outline of the current page."""
    spec = LocatorSpec(kind="css", value=":root")
    try:
        locator = await adapter.resolve_locator(page, spec)
    except Exception as exc:
        return {"outline": "", "error": "resolve_failed", "detail": str(exc)}
    try:
        result = await locator.evaluate(
            _PAGE_OUTLINE_SCRIPT,
            {"maxChars": int(max_chars), "focusText": str(focus_text or "")},
        )
    except Exception as exc:
        return {"outline": "", "error": "evaluate_failed", "detail": str(exc)}
    if not isinstance(result, dict):
        return {"outline": str(result) if result is not None else "", "raw": True}
    return result


async def _exec_inspect(
    adapter: AutomationAdapter,
    page: Any,
    xpath: str,
    max_items: int,
) -> dict[str, Any]:
    if not xpath:
        return {"matches": [], "error": "empty_xpath"}
    max_items = max(1, min(5, int(max_items or 3)))
    spec = LocatorSpec(kind="xpath", value=xpath)
    try:
        locator = await adapter.resolve_locator(page, spec)
        count = await locator.count()
    except Exception as exc:
        return {"matches": [], "count": 0, "error": "resolve_failed", "detail": str(exc)}

    matches: list[dict[str, Any]] = []
    upper = min(int(count or 0), max_items)
    for idx in range(upper):
        try:
            entry = await locator.nth(idx).evaluate(_INSPECT_SCRIPT)
        except Exception as exc:
            matches.append({"index": idx, "error": "evaluate_failed", "detail": str(exc)})
            continue
        if isinstance(entry, list) and entry:
            payload = entry[0]
        elif isinstance(entry, dict):
            payload = entry
        else:
            payload = {"raw": entry}
        payload["index"] = idx
        matches.append(payload)
    return {"matches": matches, "count": int(count or 0)}
