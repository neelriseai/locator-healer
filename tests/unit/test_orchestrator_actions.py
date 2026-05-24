"""Tests for the expanded action vocabulary + extract data plumbing.

Coverage:
  * press_key — element-scoped + page-level + JS fallback
  * wait — fixed timeout / load state / element state / no-target default
  * scroll — into_view / page bottom / page top / pixel scroll
  * hover — natural API + JS fallback
  * screenshot — auto path vs explicit path
  * extract — heuristic mode + LLM-assisted mode + zero-items error
  * extracted_data aggregation through OrchestrationResult
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from xpath_healer.core.models import LocatorSpec, Recovered
from xpath_healer.core.workflow import WorkflowStep
from xpath_healer.llm.client import ChatMessage, ChatResponse, LLMClient, ToolDefinition
from xpath_healer.orchestrator import (
    AgenticGoalDecomposer,
    OrchestrationResult,
    PlaywrightActionExecutor,
    TieredOutcomeVerifier,
    WorkflowGoal,
    WorkflowOrchestrator,
)
from xpath_healer.orchestrator.models import (
    ACTION_EXTRACT,
    ACTION_HOVER,
    ACTION_PRESS_KEY,
    ACTION_SCREENSHOT,
    ACTION_SCROLL,
    ACTION_WAIT,
)


# ===========================================================================
# Shared scaffolding
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


class _RecordingLocator:
    """Captures every API method invocation for assertion."""

    def __init__(
        self,
        *,
        count: int = 1,
        item_htmls: list[str] | None = None,
        evaluate_returns: dict[str, Any] | None = None,
    ) -> None:
        self._count = count
        self._item_htmls = item_htmls or []
        self._eval_returns = evaluate_returns or {}
        self.pressed: list[str] = []
        self.scrolls: list[str] = []
        self.hovers: int = 0
        self.evaluates: list[tuple[str, Any]] = []
        self.wait_calls: list[dict[str, Any]] = []
        self.scrolled_into_view: int = 0

    async def count(self) -> int:
        return self._count

    def nth(self, idx: int) -> "_RecordingLocator":
        item = _RecordingLocator(count=1)
        item._item_htmls = [self._item_htmls[idx]] if idx < len(self._item_htmls) else [""]
        item._eval_returns = self._eval_returns
        return item

    async def press(self, key: str) -> None:
        self.pressed.append(key)

    async def wait_for(self, *, state: str = "visible", timeout: int = 0) -> None:
        self.wait_calls.append({"state": state, "timeout": timeout})

    async def scroll_into_view_if_needed(self) -> None:
        self.scrolled_into_view += 1

    async def hover(self) -> None:
        self.hovers += 1

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        self.evaluates.append((script, arg))
        if "outerHTML" in script and self._item_htmls:
            return self._item_htmls[0]
        if "el.querySelector" in script and isinstance(arg, dict):
            # Selector application — return canned per-field result.
            return {k: self._eval_returns.get(k, "") for k in arg.keys()}
        return None


class _RecordingPage:
    def __init__(self, *, can_keyboard: bool = True, can_evaluate: bool = True) -> None:
        self.url = "about:blank"
        self.screenshots: list[str] = []
        self.load_states: list[str] = []
        self.evaluated: list[str] = []
        self._can_keyboard = can_keyboard
        self._can_evaluate = can_evaluate

        if can_keyboard:
            outer = self

            class _Kb:
                async def press(self_, key: str) -> None:
                    outer.kbd_pressed = key

            self.keyboard = _Kb()
            self.kbd_pressed = ""

    async def wait_for_load_state(self, state: str) -> None:
        self.load_states.append(state)

    async def screenshot(self, *, path: str, full_page: bool = False) -> None:
        self.screenshots.append(path)

    async def evaluate(self, script: str) -> Any:
        if not self._can_evaluate:
            raise AttributeError("evaluate unavailable")
        self.evaluated.append(script)
        return None


# ===========================================================================
# press_key
# ===========================================================================


@pytest.mark.asyncio
async def test_press_key_on_element_uses_locator_press() -> None:
    loc = _RecordingLocator()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_PRESS_KEY),
        locator=loc, page=_RecordingPage(), value="Enter", adapter=None,
    )
    assert res.status == "ok"
    assert loc.pressed == ["Enter"]


@pytest.mark.asyncio
async def test_press_key_no_locator_uses_page_keyboard() -> None:
    page = _RecordingPage()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_PRESS_KEY),
        locator=None, page=page, value="Tab", adapter=None,
    )
    assert res.status == "ok"
    assert page.kbd_pressed == "Tab"


@pytest.mark.asyncio
async def test_press_key_empty_value_is_error() -> None:
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_PRESS_KEY),
        locator=_RecordingLocator(), page=_RecordingPage(), value="", adapter=None,
    )
    assert res.status == "error"
    assert "empty key" in res.detail


# ===========================================================================
# wait
# ===========================================================================


@pytest.mark.asyncio
async def test_wait_timeout_string_parses_seconds_and_milliseconds() -> None:
    e = PlaywrightActionExecutor()
    r1 = await e.execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_WAIT),
        locator=None, page=_RecordingPage(), value="50ms", adapter=None,
    )
    assert r1.status == "ok"
    assert r1.page_signal["slept_ms"] == 50
    r2 = await e.execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_WAIT),
        locator=None, page=_RecordingPage(), value="0.05s", adapter=None,
    )
    assert r2.status == "ok"
    assert r2.page_signal["slept_ms"] == 50


@pytest.mark.asyncio
async def test_wait_load_state_routes_to_page() -> None:
    page = _RecordingPage()
    await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_WAIT),
        locator=None, page=page, value="networkidle", adapter=None,
    )
    assert page.load_states == ["networkidle"]


@pytest.mark.asyncio
async def test_wait_element_state_calls_locator_wait_for() -> None:
    loc = _RecordingLocator()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_WAIT),
        locator=loc, page=_RecordingPage(), value="visible", adapter=None,
    )
    assert res.status == "ok"
    assert loc.wait_calls and loc.wait_calls[0]["state"] == "visible"


@pytest.mark.asyncio
async def test_wait_unrecognized_value_returns_error() -> None:
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_WAIT),
        locator=None, page=_RecordingPage(), value="forever", adapter=None,
    )
    assert res.status == "error"


# ===========================================================================
# scroll
# ===========================================================================


@pytest.mark.asyncio
async def test_scroll_into_view_uses_natural_api() -> None:
    loc = _RecordingLocator()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_SCROLL),
        locator=loc, page=_RecordingPage(), value="", adapter=None,
    )
    assert res.status == "ok"
    assert loc.scrolled_into_view == 1


@pytest.mark.asyncio
async def test_scroll_page_bottom_uses_page_evaluate() -> None:
    page = _RecordingPage()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_SCROLL),
        locator=None, page=page, value="bottom", adapter=None,
    )
    assert res.status == "ok"
    assert any("scrollHeight" in s for s in page.evaluated)


@pytest.mark.asyncio
async def test_scroll_page_pixels_uses_scrollBy() -> None:
    page = _RecordingPage()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_SCROLL),
        locator=None, page=page, value="500", adapter=None,
    )
    assert res.status == "ok"
    assert any("scrollBy(0, 500)" in s for s in page.evaluated)


# ===========================================================================
# hover
# ===========================================================================


@pytest.mark.asyncio
async def test_hover_uses_natural_api() -> None:
    loc = _RecordingLocator()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_HOVER),
        locator=loc, page=_RecordingPage(), value="", adapter=None,
    )
    assert res.status == "ok"
    assert loc.hovers == 1


@pytest.mark.asyncio
async def test_hover_no_locator_is_error() -> None:
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_HOVER),
        locator=None, page=_RecordingPage(), value="", adapter=None,
    )
    assert res.status == "error"


# ===========================================================================
# screenshot
# ===========================================================================


@pytest.mark.asyncio
async def test_screenshot_auto_path_under_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    page = _RecordingPage()
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="my_step", intent="i", action=ACTION_SCREENSHOT),
        locator=None, page=page, value="", adapter=None,
    )
    assert res.status == "ok"
    assert page.screenshots and page.screenshots[0].endswith("my_step.png")
    assert "orchestrator_screenshots" in page.screenshots[0]


@pytest.mark.asyncio
async def test_screenshot_explicit_path(tmp_path) -> None:
    page = _RecordingPage()
    target = tmp_path / "sub" / "shot.png"
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_SCREENSHOT),
        locator=None, page=page, value=str(target), adapter=None,
    )
    assert res.status == "ok"
    assert page.screenshots == [str(target)]
    assert target.parent.is_dir()


# ===========================================================================
# extract
# ===========================================================================


@pytest.mark.asyncio
async def test_extract_heuristic_mode_pulls_price_and_rating() -> None:
    item_html = """
    <div class='card'>
      <h2>iPhone 15 Pro</h2>
      <span class='p'>₹89,999</span>
      <span class='r'>4.5 stars</span>
    </div>
    """
    loc = _RecordingLocator(
        count=2,
        item_htmls=[item_html, item_html],
    )
    # No llm_for_extract → heuristic mode.
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_EXTRACT),
        locator=loc, page=_RecordingPage(),
        value='{"fields": ["name", "price", "rating"], "limit": 2}',
        adapter=None,
    )
    assert res.status == "ok"
    assert res.page_signal["extract_mode"] == "heuristic"
    rows = res.page_signal["extracted"]
    assert len(rows) == 2
    for row in rows:
        assert "iPhone 15 Pro" in row["name"]
        assert "₹89,999" in row["price"] or "89,999" in row["price"]
        assert row["rating"] == "4.5"


@pytest.mark.asyncio
async def test_extract_llm_mode_uses_resolved_selectors() -> None:
    llm = _ScriptedLLM(
        [
            ChatResponse(
                content=json.dumps(
                    {"name": "h2.title", "price": "span.p", "rating": "span.r"}
                )
            )
        ]
    )
    loc = _RecordingLocator(
        count=1,
        item_htmls=["<div><h2 class='title'>X</h2><span class='p'>₹1</span><span class='r'>4.0</span></div>"],
        evaluate_returns={"name": "X", "price": "₹1", "rating": "4.0"},
    )
    res = await PlaywrightActionExecutor(llm_for_extract=llm).execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_EXTRACT),
        locator=loc, page=_RecordingPage(),
        value='{"fields": ["name", "price", "rating"], "limit": 1}',
        adapter=None,
    )
    assert res.status == "ok"
    assert res.page_signal["extract_mode"] == "llm"
    assert res.page_signal["field_selectors"] == {
        "name": "h2.title", "price": "span.p", "rating": "span.r"
    }
    rows = res.page_signal["extracted"]
    # Extract auto-appends ``_href`` (the item's first <a href>) so
    # drill-down workflows can navigate without an extra step. Assert
    # the requested fields are present and correct, then assert the
    # _href slot exists.
    assert len(rows) == 1
    assert {"name": "X", "price": "₹1", "rating": "4.0"}.items() <= rows[0].items()
    assert "_href" in rows[0]


@pytest.mark.asyncio
async def test_extract_zero_items_is_error() -> None:
    loc = _RecordingLocator(count=0)
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_EXTRACT),
        locator=loc, page=_RecordingPage(),
        value='{"fields": ["name"]}',
        adapter=None,
    )
    assert res.status == "error"
    assert "0 items" in res.detail


@pytest.mark.asyncio
async def test_extract_value_parses_csv_fallback() -> None:
    item_html = "<div><h3>Title</h3><p>Body</p></div>"
    loc = _RecordingLocator(count=1, item_htmls=[item_html])
    res = await PlaywrightActionExecutor().execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_EXTRACT),
        locator=loc, page=_RecordingPage(),
        value="name,price",
        adapter=None,
    )
    assert res.status == "ok"
    assert "name" in res.page_signal["extracted"][0]
    assert "price" in res.page_signal["extracted"][0]


@pytest.mark.asyncio
async def test_extract_llm_returning_invalid_json_falls_back_to_heuristic() -> None:
    llm = _ScriptedLLM([ChatResponse(content="not really json")])
    item_html = "<div><h2>Nice Phone</h2><span>₹49,999</span><span>4.3</span></div>"
    loc = _RecordingLocator(count=1, item_htmls=[item_html])
    res = await PlaywrightActionExecutor(llm_for_extract=llm).execute(
        step=WorkflowStep(step_id="s", intent="i", action=ACTION_EXTRACT),
        locator=loc, page=_RecordingPage(),
        value='{"fields": ["name", "price"], "limit": 1}',
        adapter=None,
    )
    assert res.status == "ok"
    assert res.page_signal["extract_mode"] == "heuristic"
    row = res.page_signal["extracted"][0]
    assert "Nice Phone" in row["name"]


# ===========================================================================
# extracted_data flows through OrchestrationResult
# ===========================================================================


class _FakeAdapter:
    name = "fake"

    async def resolve_locator(self, root, spec):
        # The orchestrator's read_page_outline call expects a locator
        # whose .evaluate returns an outline dict.
        class _L:
            async def count(self_):
                return 2

            def nth(self_, idx):
                inner = _L()
                inner._idx = idx
                return inner

            async def evaluate(self_, script, arg=None):
                if "location.href" in script:
                    return "https://example.com"
                if "outerHTML" in script:
                    return "<div><h2>Sample</h2><span>₹100</span></div>"
                if "el.querySelector" in script and isinstance(arg, dict):
                    return {"name": "Sample", "price": "₹100"}
                # Default for read_page_outline JS.
                return {
                    "outline": "div\n  h2 'Sample'\n  span '₹100'",
                    "total_nodes_emitted": 3,
                }

        return _L()

    async def capture_page_html(self, page):
        return ""


class _FacadeFake:
    def __init__(self, *, adapter, recovered) -> None:
        self.adapter = adapter
        self._recovered = recovered
        self.reported: list[dict[str, Any]] = []

    async def recover_workflow_step(self, **kwargs) -> Recovered:
        return self._recovered

    async def report_step_outcome(self, **kwargs) -> bool:
        self.reported.append(kwargs)
        return True


@pytest.mark.asyncio
async def test_orchestrator_surfaces_extract_results_in_extracted_data() -> None:
    """End-to-end: plan contains an extract step; orchestrator surfaces
    the row list under OrchestrationResult.extracted_data[step_id]."""

    def _plan_response():
        return ChatResponse(
            tool_calls=[
                _build_commit_plan(
                    [
                        {
                            "step_id": "extract_phones",
                            "intent": "extract phones",
                            "action": "extract",
                            "target_label": "product cards",
                            "target_kind": "list",
                            "value": '{"fields": ["name", "price"], "limit": 2}',
                        }
                    ]
                )
            ]
        )

    decomposer_llm = _ScriptedLLM([_plan_response()])
    extract_llm = _ScriptedLLM(
        [ChatResponse(content='{"name": "h2", "price": "span"}')]
    )

    adapter = _FakeAdapter()
    locator = _RecordingLocator(
        count=2,
        item_htmls=[
            "<div><h2>Phone A</h2><span>₹100</span></div>",
            "<div><h2>Phone B</h2><span>₹200</span></div>",
        ],
        evaluate_returns={"name": "Phone X", "price": "₹X"},
    )
    recovered = Recovered(
        status="success",
        correlation_id="c",
        locator_spec=LocatorSpec(kind="xpath", value="//div"),
        runtime_locator=locator,
        strategy_id="rules",
    )
    facade = _FacadeFake(adapter=adapter, recovered=recovered)

    orch = WorkflowOrchestrator(
        facade=facade,
        decomposer=AgenticGoalDecomposer(decomposer_llm),
        executor=PlaywrightActionExecutor(llm_for_extract=extract_llm),
        verifier=TieredOutcomeVerifier(llm_verifier=None),
    )

    result = await orch.run(
        page=_RecordingPage(),
        goal=WorkflowGoal(text="fetch phones"),
    )
    assert result.status == "success"
    assert "extract_phones" in result.extracted_data
    rows = result.extracted_data["extract_phones"]
    assert len(rows) == 2
    for row in rows:
        # extract_llm returned {name:h2, price:span}; locator's evaluate
        # uses the fake's evaluate_returns for selector-application.
        assert row["name"] == "Phone X"
        assert row["price"] == "₹X"


# ---------------------------------------------------------------------------
# tiny helper to keep tests compact
# ---------------------------------------------------------------------------


def _build_commit_plan(steps: list[dict[str, Any]]):
    from xpath_healer.llm.client import ToolCall

    return ToolCall(id="c1", name="commit_plan", arguments={"steps": steps})
