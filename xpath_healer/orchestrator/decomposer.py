"""Goal decomposer — NL goal + page outline → ordered WorkflowSteps."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol, runtime_checkable

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.workflow import WorkflowStep
from xpath_healer.llm.client import ChatMessage, LLMClient, ToolDefinition
from xpath_healer.mcp.explorer import _exec_read_outline
from xpath_healer.orchestrator.models import (
    ACTION_CLICK,
    ACTION_EXTRACT,
    ACTION_FILL,
    ACTION_HOVER,
    ACTION_NAVIGATE,
    ACTION_PRESS_KEY,
    ACTION_SCREENSHOT,
    ACTION_SCROLL,
    ACTION_SELECT,
    ACTION_VERIFY,
    ACTION_WAIT,
    PlannedWorkflow,
    WorkflowGoal,
    is_known_action,
)


_SYSTEM_PROMPT = (
    "You are a workflow planner. Given a natural-language goal and a "
    "compact structural OUTLINE of the current page, emit a JSON plan "
    "that the orchestrator will execute step-by-step.\n\n"
    "COMPLETENESS: the plan MUST drive the goal end-to-end. If the goal "
    "says 'search for X then read N results', the plan needs the search "
    "step AND the wait-for-results step AND the extract step. Do not "
    "stop after a single navigate or single click — those alone never "
    "accomplish a real goal.\n\n"
    "MULTI-PAGE WORKFLOWS: search → results, login → dashboard, list → "
    "product detail all involve targets you cannot yet see in this "
    "outline. Plan them anyway with PROVISIONAL target_labels drawn "
    "from the goal vocabulary ('product cards', 'first result', "
    "'add to cart button', 'price'). The orchestrator's healer will "
    "resolve them on the next page; the orchestrator will also "
    "re-decompose mid-run if the page changes drastically.\n\n"
    "SEARCH INPUTS: when the outline shows a search input but no clear "
    "'Submit' / 'Search' BUTTON near it, prefer one `press_key` step "
    "with value='Enter' (target=that search input) over guessing a "
    "click target. Amazon, Google, Flipkart all submit on Enter.\n\n"
    "RICH QUERIES OVER FILTER CLICKS: when the goal mentions a price "
    "ceiling, brand, color, or category alongside a search term, type "
    "the WHOLE phrase into the search box (e.g. fill 'mobile phones "
    "under 50000', not 'mobile phones' then click '< Rs 50000' filter). "
    "Search engines parse these natural-language modifiers reliably "
    "and the resulting URL is more stable than chasing facet panels "
    "that load asynchronously. Only plan filter clicks when the goal "
    "explicitly demands a specific facet (e.g. 'apply the Newest sort').\n\n"
    "SORT INFERENCE: when the goal asks for 'cheapest', 'lowest price', "
    "'most expensive', 'best rated', 'newest', 'latest', or 'most "
    "popular' results, ADD a sort step AFTER the search completes "
    "(after a wait for results). Target the visible sort control "
    "('Sort by', 'Price', etc.) and value the matching label "
    "('Price: Low to High', 'Price: High to Low', 'Newest', 'Avg "
    "Customer Review'). Many sites also reflect the choice in the URL "
    "(?sort=price-asc) but always prefer the UI control because the "
    "URL parameter changes per site.\n\n"
    "DELIVERY-AGNOSTIC GOALS: if the goal is about browsing / "
    "comparing / extracting product info AND does not mention "
    "checkout, delivery, or address, ALWAYS dismiss location / "
    "address / pincode popups with optional click steps and proceed "
    "without setting a delivery address. The goal does not need a "
    "shipping target; setting one risks resetting the search.\n\n"
    "STRICT RULES (every plan must satisfy these):\n"
    "  * For steps targeting elements visible in THIS outline, "
    "target_label MUST be drawn from the outline. For provisional "
    "next-page steps (extract / wait-for-results / drill-down click), "
    "use natural-language labels the model can resolve via the heal "
    "cascade later.\n"
    "  * target_label MUST be a short HUMAN-READABLE string a user would "
    "see — e.g. 'Email', 'Search for Products', 'Submit', 'Add to Cart'. "
    "It must NEVER be a structural descriptor like 'input[name=q,type=text,"
    "ph=...]' or 'div._1AtVbE'. The outline lines look like "
    "`tag[attrs] \\\"Visible Text\\\"` — copy ONLY the quoted Visible "
    "Text into target_label. For inputs without inline text, use the "
    "placeholder / aria-label text that appears in quotes after the "
    "attribute brackets.\n"
    "  * AUTO-DISMISS POPUPS / MODALS: when the outline shows a login, "
    "sign-in, cookie banner, app-install, or marketing popup AND the "
    "VALUES dict has no credentials for that site, plan a `click` step "
    "with optional=true that targets the close/dismiss control "
    "('Close', '\\u00d7', 'Not now', 'No thanks', 'Maybe later', "
    "'Continue without login'). Place these dismiss steps BEFORE the "
    "main task steps so the page is clear. Never plan steps that ask "
    "for credentials when none are supplied. EVERY dismiss-style step "
    "MUST have optional=true — a missing popup means there was nothing "
    "to dismiss, which is fine, the workflow continues. Never make a "
    "dismiss step required.\n"
    "  * Action verb must be one of:\n"
    "      - 'navigate'   : open a URL (value=URL). Locator-less.\n"
    "      - 'fill'       : type value into an input/textarea.\n"
    "      - 'click'      : click button / link / checkbox / radio.\n"
    "      - 'select'     : choose an option from a dropdown (value=label or value).\n"
    "      - 'press_key'  : keyboard input (value=Enter|Escape|Tab|ArrowDown...).\n"
    "      - 'hover'      : mouse hover (menus / tooltips).\n"
    "      - 'wait'       : value can be '500ms' / '2s' / 'visible' / "
    "'hidden' / 'networkidle' / 'domcontentloaded'. With no target_label "
    "it's a page-level wait.\n"
    "      - 'scroll'     : value 'into_view' (default with locator) / "
    "'bottom' / 'top' / pixel count like '800'.\n"
    "      - 'screenshot' : capture artifact (value=optional path).\n"
    "      - 'verify'     : read-only assertion (no locator action).\n"
    "      - 'extract'    : pull structured data from a LIST of items. "
    "target_label points at the list container (e.g. 'product cards'); "
    "value MUST be a JSON object: "
    '{"fields":["name","price","rating"],"limit":5}\n'
    "  * Pull literal values (emails, search queries, prices) from the "
    "goal text and the VALUES dict; never invent values.\n"
    "  * Order matters — every step's preconditions must be satisfied "
    "by prior steps. Use 'wait' for dynamic content; 'scroll' for "
    "lazy-loaded lists; 'press_key' with value='Enter' to submit a "
    "search input that has no explicit Submit button.\n"
    "  * Mark a step optional=true only when the workflow can still "
    "complete without it (cookie banner, marketing popup, login prompt).\n"
    "  * Keep step_ids short snake_case (e.g. 'fill_email').\n"
    "  * expected_outcome is a short observable statement the verifier "
    "can check ('email field shows alice@example.com', 'results grid "
    "is visible', 'URL contains /cart', 'see 'Add to Cart' visible').\n\n"
    "Return EXACTLY one tool call: commit_plan(steps=[...]).\n"
    "Do not reply with prose."
)


def _commit_plan_tool() -> ToolDefinition:
    return ToolDefinition(
        name="commit_plan",
        description=(
            "Submit the ordered list of workflow steps. The orchestrator "
            "will execute them sequentially through the healing layer."
        ),
        parameters={
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_id": {"type": "string"},
                            "intent": {"type": "string"},
                            "action": {
                                "type": "string",
                                "enum": [
                                    ACTION_NAVIGATE,
                                    ACTION_FILL,
                                    ACTION_CLICK,
                                    ACTION_SELECT,
                                    ACTION_VERIFY,
                                    ACTION_EXTRACT,
                                    ACTION_PRESS_KEY,
                                    ACTION_WAIT,
                                    ACTION_SCROLL,
                                    ACTION_HOVER,
                                    ACTION_SCREENSHOT,
                                ],
                            },
                            "target_label": {"type": "string"},
                            "target_kind": {"type": "string"},
                            "value": {
                                "type": "string",
                                "description": (
                                    "Literal value to fill/select/navigate. "
                                    "Empty for click/verify."
                                ),
                            },
                            "expected_outcome": {"type": "string"},
                            "optional": {"type": "boolean"},
                        },
                        "required": ["step_id", "intent", "action"],
                        "additionalProperties": False,
                    },
                    "minItems": 1,
                    "maxItems": 30,
                },
            },
            "required": ["steps"],
            "additionalProperties": False,
        },
    )


@runtime_checkable
class GoalDecomposer(Protocol):
    async def decompose(
        self,
        *,
        goal: WorkflowGoal,
        adapter: AutomationAdapter,
        page: Any,
    ) -> PlannedWorkflow:
        ...


class AgenticGoalDecomposer(GoalDecomposer):
    """Page-grounded LLM decomposer.

    Cost contract: AT MOST ``max_attempts`` LLM calls per workflow.
    Default 2 — first attempt; one retry if the model didn't produce
    a valid plan (no commit_plan call, malformed steps, etc).
    """

    def __init__(
        self,
        llm: LLMClient,
        *,
        max_attempts: int = 2,
        outline_max_chars: int = 8000,
    ) -> None:
        self.llm = llm
        self.max_attempts = max(1, int(max_attempts))
        self.outline_max_chars = int(outline_max_chars)
        self.logger = logging.getLogger("xpath_healer.orchestrator.decomposer")

    async def decompose(
        self,
        *,
        goal: WorkflowGoal,
        adapter: AutomationAdapter,
        page: Any,
    ) -> PlannedWorkflow:
        outline_payload = await self._read_outline_with_retry(adapter, page)
        outline_text = str(outline_payload.get("outline") or "")
        user_msg = self._build_user_prompt(goal, outline_text)
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_msg),
        ]
        tools = [_commit_plan_tool()]

        last_error = ""
        for attempt in range(self.max_attempts):
            try:
                response = await self.llm.chat(messages, tools=tools)
            except Exception as exc:
                self.logger.exception("Decomposer LLM call failed (attempt %d)", attempt + 1)
                last_error = f"llm_call_failed: {exc}"
                break

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=list(response.tool_calls),
                )
            )

            commit_call = next(
                (c for c in response.tool_calls if c.name == "commit_plan"),
                None,
            )
            if commit_call is None:
                last_error = "no_commit_plan_call"
                # Tell the model what went wrong; let it try again on
                # the next loop iteration.
                if response.tool_calls:
                    for c in response.tool_calls:
                        messages.append(
                            ChatMessage(
                                role="tool",
                                tool_call_id=c.id,
                                content=json.dumps({"error": "expected commit_plan"}),
                            )
                        )
                messages.append(
                    ChatMessage(
                        role="user",
                        content="You must call commit_plan(steps=[...]).",
                    )
                )
                continue

            try:
                steps, values_by_step = self._parse_steps(commit_call.arguments)
            except Exception as exc:
                last_error = f"invalid_plan: {exc}"
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=commit_call.id,
                        content=json.dumps({"error": str(exc)}),
                    )
                )
                messages.append(
                    ChatMessage(
                        role="user",
                        content="Fix the plan and call commit_plan again.",
                    )
                )
                continue

            return PlannedWorkflow(
                workflow_id=f"wf-{uuid.uuid4().hex[:12]}",
                goal=goal,
                steps=steps,
                values_by_step=values_by_step,
                metadata={
                    "decomposer": "agentic",
                    "model": (response.metadata or {}).get("model", ""),
                    "outline_chars": len(outline_text),
                    "outline_nodes": int(outline_payload.get("total_nodes_emitted") or 0),
                    "attempts": attempt + 1,
                },
            )

        # All attempts exhausted — return an empty plan with diagnostics.
        return PlannedWorkflow(
            workflow_id=f"wf-{uuid.uuid4().hex[:12]}",
            goal=goal,
            steps=[],
            values_by_step={},
            metadata={
                "decomposer": "agentic",
                "error": last_error or "unknown_failure",
                "attempts": self.max_attempts,
            },
        )

    # ------------------------------------------------------------------

    async def _read_outline_with_retry(
        self,
        adapter: AutomationAdapter,
        page: Any,
    ) -> dict[str, Any]:
        """Outline the page; if it looks empty/short, wait for network
        idle (SPA settle) and try once more. Catches the
        domcontentloaded-too-early case on heavy sites like Amazon."""
        payload = await _exec_read_outline(
            adapter, page, max_chars=self.outline_max_chars, focus_text=""
        )
        outline = str(payload.get("outline") or "")
        # Heuristic: an empty / tiny outline usually means the page is
        # mostly client-rendered and hasn't settled yet. 400 chars is
        # well below the size of any non-trivial real page outline.
        if len(outline) >= 400:
            return payload
        self.logger.info(
            "decomposer outline tiny (%d chars) — waiting for networkidle and retrying",
            len(outline),
        )
        # Best-effort wait for network idle on a Playwright Page.
        wait_for_load_state = getattr(page, "wait_for_load_state", None)
        if callable(wait_for_load_state):
            try:
                await wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                # Already past idle, or site never reaches idle. Either
                # way we'll still take a second outline below.
                pass
        # Optional second short scroll to trigger lazy content.
        try:
            evaluate = getattr(page, "evaluate", None)
            if callable(evaluate):
                await evaluate("() => { window.scrollBy(0, 300); }")
        except Exception:
            pass
        return await _exec_read_outline(
            adapter, page, max_chars=self.outline_max_chars, focus_text=""
        )

    @staticmethod
    def _build_user_prompt(goal: WorkflowGoal, outline: str) -> str:
        payload = {
            "goal": goal.text,
            "start_url": goal.start_url,
            "values": dict(goal.values),
            "constraints": dict(goal.constraints),
            "page_outline": outline or "(empty)",
        }
        return (
            "Plan the workflow described below. Ground every step in the "
            "page_outline; do not propose targets that aren't there.\n\n"
            + json.dumps(payload, ensure_ascii=True, default=str)
        )

    @staticmethod
    def _parse_steps(args: dict[str, Any]) -> tuple[list[WorkflowStep], dict[str, str]]:
        raw_steps = (args or {}).get("steps") or []
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("steps must be a non-empty list")
        steps: list[WorkflowStep] = []
        values: dict[str, str] = {}
        seen_ids: set[str] = set()
        for idx, item in enumerate(raw_steps):
            if not isinstance(item, dict):
                raise ValueError(f"step[{idx}] not an object")
            step_id = str(item.get("step_id") or "").strip()
            if not step_id:
                raise ValueError(f"step[{idx}] missing step_id")
            if step_id in seen_ids:
                raise ValueError(f"duplicate step_id: {step_id}")
            seen_ids.add(step_id)
            action = str(item.get("action") or "").strip().lower()
            if not is_known_action(action):
                raise ValueError(f"step[{idx}] action={action!r} not supported")
            intent = str(item.get("intent") or "").strip()
            if not intent:
                raise ValueError(f"step[{idx}] missing intent")
            step = WorkflowStep(
                step_id=step_id,
                intent=intent,
                action=action,
                target_label=str(item.get("target_label") or ""),
                target_kind=str(item.get("target_kind") or ""),
                expected_outcome=str(item.get("expected_outcome") or ""),
                optional=bool(item.get("optional") or False),
            )
            steps.append(step)
            value = str(item.get("value") or "")
            if value:
                values[step_id] = value
        return steps, values
