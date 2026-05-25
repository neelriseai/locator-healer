"""Phase 3 — AgenticMCPExplorer + healing_service mcp_explore stage.

The tests use a scripted ``LLMClient`` so the agent loop runs
deterministically without an API key. They cover:

* commit path — model emits ``commit_locator`` → result has 1 locator
* multi-commit ranking — confidences sorted descending
* tool dispatch — count_matches / inspect_matches return JSON payloads
  that the model consumes in its next turn
* no-commit fallthrough — model never commits → empty result
* max-rounds budget — explorer stops without exceeding configured cap
* first-time element — explorer runs with ``existing_meta=None``
* both adapters — the same explorer instance serves Selenium and
  Playwright callers (the explorer only depends on the adapter contract)
* healing_service wiring — ``_mcp_explore_candidates`` converts
  ``ExplorationResult`` to ``CandidateSpec`` with the correct
  ``strategy_id`` and metadata
"""

from __future__ import annotations

from typing import Any

import pytest

from xpath_healer.core.healing_service import HealingService
from xpath_healer.core.models import (
    BuildInput,
    ElementMeta,
    ElementSignature,
    Intent,
    LocatorSpec,
)
from xpath_healer.llm.client import (
    ChatMessage,
    ChatResponse,
    LLMClient,
    ToolCall,
    ToolDefinition,
)
from xpath_healer.mcp import AgenticMCPExplorer, ExplorationResult


# ---------------------------------------------------------------------------
# Scripted LLM
# ---------------------------------------------------------------------------


class _ScriptedLLM(LLMClient):
    """Replays a fixed sequence of ``ChatResponse`` objects, one per turn.

    Also records every ``messages`` payload it received so a test can
    assert on the conversation that was built.
    """

    def __init__(self, responses: list[ChatResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self._responses:
            return ChatResponse(content="", tool_calls=[])
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# Scripted adapter — enough surface for the explorer's tool dispatch.
# ---------------------------------------------------------------------------


class _FakeRuntimeLocator:
    def __init__(self, count: int, inspect_payload: list[dict[str, Any]] | None = None) -> None:
        self._count = count
        self._inspect = inspect_payload or []

    async def count(self) -> int:
        return self._count

    def nth(self, idx: int) -> "_FakeRuntimeLocator":
        # For inspect: return a locator whose .evaluate() yields one
        # element dict — explorer slices into [0].
        payload = [self._inspect[idx]] if idx < len(self._inspect) else []
        return _FakeRuntimeLocator(count=1 if payload else 0, inspect_payload=payload)

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        return self._inspect

    async def is_visible(self) -> bool:
        return True

    async def is_enabled(self) -> bool:
        return True

    async def bounding_box(self) -> dict[str, float] | None:
        return {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}


class _ScriptedAdapter:
    """Returns scripted locator responses keyed by xpath."""

    name = "scripted"

    def __init__(self) -> None:
        self._responses: dict[str, _FakeRuntimeLocator] = {}
        self.resolved: list[str] = []

    def script(self, xpath: str, *, count: int, inspect: list[dict[str, Any]] | None = None) -> None:
        self._responses[xpath] = _FakeRuntimeLocator(count=count, inspect_payload=inspect or [])

    async def resolve_locator(self, root: Any, locator_spec: LocatorSpec) -> _FakeRuntimeLocator:
        self.resolved.append(locator_spec.value)
        return self._responses.get(locator_spec.value, _FakeRuntimeLocator(count=0))

    async def capture_page_html(self, page: Any) -> str:
        return "<html></html>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_input(label: str = "Country", field_type: str = "dropdown") -> BuildInput:
    return BuildInput(
        page=object(),
        app_id="app",
        page_name="checkout",
        element_name="country_select",
        field_type=field_type,
        fallback=LocatorSpec(kind="xpath", value="//missing"),
        vars={"label": label},
        intent=Intent(label=label),
    )


def _meta_with_signature() -> ElementMeta:
    return ElementMeta(
        app_id="app",
        page_name="checkout",
        element_name="country_select",
        field_type="dropdown",
        signature=ElementSignature(
            tag="select",
            stable_attrs={"name": "country"},
            short_text="country",
            option_set={"values": ["us", "ca"]},
        ),
    )


def _commit_call(call_id: str, xpath: str, *, confidence: float, reason: str = "") -> ToolCall:
    return ToolCall(
        id=call_id,
        name="commit_locator",
        arguments={"xpath": xpath, "confidence": confidence, "reason": reason},
    )


# ---------------------------------------------------------------------------
# Agent loop tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_only_returns_single_locator_with_confidence() -> None:
    llm = _ScriptedLLM([
        ChatResponse(tool_calls=[_commit_call("c1", "//*[@id='country-new']", confidence=0.95, reason="testid match")])
    ])
    explorer = AgenticMCPExplorer(llm)
    adapter = _ScriptedAdapter()
    result = await explorer.explore(adapter, page=object(), inp=_build_input(), existing_meta=_meta_with_signature())
    assert result.rounds == 1
    assert result.tool_calls_made == 1
    assert len(result.locators) == 1
    assert result.locators[0].kind == "xpath"
    assert result.locators[0].value == "//*[@id='country-new']"
    assert result.locators[0].options["_mcp_confidence"] == 0.95
    assert result.locators[0].options["_mcp_reason"] == "testid match"


@pytest.mark.asyncio
async def test_multi_commit_results_ranked_by_confidence_desc() -> None:
    llm = _ScriptedLLM([
        ChatResponse(
            tool_calls=[
                _commit_call("c1", "//*[@id='weaker']", confidence=0.4),
                _commit_call("c2", "//*[@id='stronger']", confidence=0.9),
            ]
        )
    ])
    explorer = AgenticMCPExplorer(llm, max_commit_count=5)
    result = await explorer.explore(_ScriptedAdapter(), object(), _build_input(), None)
    assert [loc.value for loc in result.locators] == [
        "//*[@id='stronger']",
        "//*[@id='weaker']",
    ]


@pytest.mark.asyncio
async def test_count_matches_then_commit_uses_adapter() -> None:
    # Turn 1: model asks count_matches for a guess.
    # Turn 2: model sees count=1 result and commits.
    adapter = _ScriptedAdapter()
    adapter.script("//*[@id='country-new']", count=1)
    llm = _ScriptedLLM([
        ChatResponse(
            tool_calls=[ToolCall(id="t1", name="count_matches", arguments={"xpath": "//*[@id='country-new']"})]
        ),
        ChatResponse(
            tool_calls=[_commit_call("c1", "//*[@id='country-new']", confidence=0.85)]
        ),
    ])
    explorer = AgenticMCPExplorer(llm)
    result = await explorer.explore(adapter, object(), _build_input(), None)
    assert result.rounds == 2
    assert result.tool_calls_made == 2
    assert adapter.resolved == ["//*[@id='country-new']"]
    assert len(result.locators) == 1


@pytest.mark.asyncio
async def test_no_commit_returns_empty_after_one_round_of_prose() -> None:
    llm = _ScriptedLLM([ChatResponse(content="I am not sure", tool_calls=[])])
    explorer = AgenticMCPExplorer(llm)
    result = await explorer.explore(_ScriptedAdapter(), object(), _build_input(), None)
    assert result.locators == []
    assert result.rounds == 1


@pytest.mark.asyncio
async def test_max_rounds_budget_caps_loop() -> None:
    # Model never commits — only requests tools. Should stop at max_rounds.
    looping = ChatResponse(
        tool_calls=[ToolCall(id="t", name="count_matches", arguments={"xpath": "//foo"})]
    )
    adapter = _ScriptedAdapter()
    adapter.script("//foo", count=0)
    llm = _ScriptedLLM([looping] * 10)  # Plenty for the cap
    explorer = AgenticMCPExplorer(llm, max_rounds=3, max_tool_calls=100)
    result = await explorer.explore(adapter, object(), _build_input(), None)
    assert result.rounds == 3
    assert result.locators == []


@pytest.mark.asyncio
async def test_read_page_outline_is_registered_first_in_default_tools() -> None:
    """Order matters — the agent's natural instinct is to call the first
    listed tool first. read_page_outline must come before probes so the
    LLM sees the page layout before guessing."""
    from xpath_healer.mcp.explorer import build_default_tools

    tools = build_default_tools()
    names = [t.name for t in tools]
    assert names[0] == "read_page_outline"
    assert "count_matches" in names
    assert "inspect_matches" in names
    assert "commit_locator" in names


@pytest.mark.asyncio
async def test_read_page_outline_dispatch_returns_outline_payload() -> None:
    """When the model calls read_page_outline, dispatch should route to
    the executor and pass through max_chars / focus_text."""
    captured_args: dict[str, Any] = {}

    class _OutlineAdapter:
        name = "outline-fake"

        async def resolve_locator(self, root, spec):
            class _L:
                async def count(self_):
                    return 1

                def nth(self_, idx):
                    return self_

                async def evaluate(self_, script, arg=None):
                    captured_args["script"] = script
                    captured_args["arg"] = arg
                    return {
                        "outline": "form\n  input[name=email]",
                        "total_nodes_emitted": 2,
                        "total_nodes_considered": 5,
                        "focus_text": (arg or {}).get("focusText", ""),
                    }

            return _L()

    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="t1",
                        name="read_page_outline",
                        arguments={"max_chars": 4000, "focus_text": "Email"},
                    )
                ]
            ),
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="commit_locator",
                        arguments={"xpath": "//input[@name='email']", "confidence": 0.95},
                    )
                ]
            ),
        ]
    )
    explorer = AgenticMCPExplorer(llm)
    result = await explorer.explore(_OutlineAdapter(), object(), _build_input(), None)

    assert "script" in captured_args
    # arg passed to evaluate must carry our maxChars/focusText
    assert captured_args["arg"] == {"maxChars": 4000, "focusText": "Email"}
    # The tool response gets serialised into the assistant context — the
    # explorer should have made it to the commit phase next turn.
    assert len(result.locators) == 1
    assert result.locators[0].value == "//input[@name='email']"


@pytest.mark.asyncio
async def test_read_page_outline_dispatch_defaults_max_chars_when_missing() -> None:
    """When the model omits max_chars / focus_text, the executor must
    fall back to its defaults so the call doesn't crash."""
    captured: dict[str, Any] = {}

    class _Adp:
        name = "fake"

        async def resolve_locator(self, root, spec):
            class _L:
                async def count(self_):
                    return 1

                def nth(self_, idx):
                    return self_

                async def evaluate(self_, script, arg=None):
                    captured["arg"] = arg
                    return {"outline": "html"}

            return _L()

    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(id="t1", name="read_page_outline", arguments={})
                ]
            ),
            ChatResponse(tool_calls=[_commit_call("c1", "//x", confidence=0.8)]),
        ]
    )
    explorer = AgenticMCPExplorer(llm)
    await explorer.explore(_Adp(), object(), _build_input(), None)
    assert captured["arg"]["maxChars"] == 8000
    assert captured["arg"]["focusText"] == ""


@pytest.mark.asyncio
async def test_read_page_outline_resolve_failure_is_graceful() -> None:
    """If the adapter can't even resolve :root, the outline tool returns
    an error dict and the loop continues."""
    class _BrokenAdapter:
        name = "broken"

        async def resolve_locator(self, root, spec):
            raise RuntimeError("no document")

    llm = _ScriptedLLM(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(id="t1", name="read_page_outline", arguments={"max_chars": 1000})
                ]
            ),
            ChatResponse(tool_calls=[_commit_call("c1", "//x", confidence=0.6)]),
        ]
    )
    explorer = AgenticMCPExplorer(llm)
    result = await explorer.explore(_BrokenAdapter(), object(), _build_input(), None)
    # Loop survived and committed.
    assert len(result.locators) == 1


@pytest.mark.asyncio
async def test_system_prompt_includes_deterministic_playbook() -> None:
    """Sanity: the playbook text must be in the system prompt so the
    model sees the strategy patterns rather than guessing."""
    from xpath_healer.mcp.explorer import _SYSTEM_PROMPT

    assert "DETERMINISTIC PLAYBOOK" in _SYSTEM_PROMPT
    assert "label[@for]" in _SYSTEM_PROMPT
    assert "container-scoped" in _SYSTEM_PROMPT
    assert "tree/expand" in _SYSTEM_PROMPT
    assert "PRIORITY ORDER" in _SYSTEM_PROMPT
    assert "data-testid" in _SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_unknown_tool_returned_does_not_break_loop() -> None:
    llm = _ScriptedLLM([
        ChatResponse(tool_calls=[ToolCall(id="t1", name="hallucinated_tool", arguments={})]),
        ChatResponse(tool_calls=[_commit_call("c1", "//*[@id='ok']", confidence=0.7)]),
    ])
    explorer = AgenticMCPExplorer(llm)
    result = await explorer.explore(_ScriptedAdapter(), object(), _build_input(), None)
    assert len(result.locators) == 1
    assert result.locators[0].value == "//*[@id='ok']"


@pytest.mark.asyncio
async def test_first_time_element_explore_works_with_no_prior_memory() -> None:
    """User asked: 'should agent heal for elements which are added newly'.

    Yes — the explorer accepts existing_meta=None and the LLM still
    receives a prompt with intent + label + field_type.
    """
    llm = _ScriptedLLM([
        ChatResponse(tool_calls=[_commit_call("c1", "//button[normalize-space()='Save']", confidence=0.8)])
    ])
    explorer = AgenticMCPExplorer(llm)
    inp = _build_input(label="Save", field_type="button")
    result = await explorer.explore(_ScriptedAdapter(), object(), inp, existing_meta=None)
    assert len(result.locators) == 1
    # Inspect the prompt sent on turn 1: prior_memory must be null.
    user_msg = llm.calls[0]["messages"][1]
    assert user_msg.role == "user"
    assert '"prior_memory":null' in user_msg.content.replace(" ", "")


@pytest.mark.asyncio
async def test_explorer_works_for_selenium_style_adapter() -> None:
    """The explorer talks to the adapter contract only — Selenium and
    Playwright adapters both satisfy it, so the same explorer instance
    serves both runtimes without per-adapter glue."""
    # We don't actually instantiate the real Selenium adapter (no driver);
    # the point is that the explorer uses .resolve_locator + .count +
    # .evaluate, all of which both real adapters implement.
    adapter = _ScriptedAdapter()
    adapter.script("//*[@data-testid='save']", count=1)
    llm = _ScriptedLLM([
        ChatResponse(
            tool_calls=[ToolCall(id="t1", name="count_matches", arguments={"xpath": "//*[@data-testid='save']"})]
        ),
        ChatResponse(tool_calls=[_commit_call("c1", "//*[@data-testid='save']", confidence=0.9)]),
    ])
    explorer = AgenticMCPExplorer(llm)
    result = await explorer.explore(adapter, object(), _build_input(label="Save", field_type="button"), None)
    assert len(result.locators) == 1
    # Adapter was invoked — proves the explorer goes through the contract.
    assert "//*[@data-testid='save']" in adapter.resolved


# ---------------------------------------------------------------------------
# healing_service wiring
# ---------------------------------------------------------------------------


class _FakeContext:
    """Minimal StrategyContext-shaped stub."""

    def __init__(self, adapter: _ScriptedAdapter, explorer: AgenticMCPExplorer) -> None:
        self.adapter = adapter
        self.mcp_assist = explorer
        import logging

        self.logger = logging.getLogger("test")


@pytest.mark.asyncio
async def test_mcp_explore_candidates_wraps_results_as_candidate_specs() -> None:
    llm = _ScriptedLLM([
        ChatResponse(
            tool_calls=[
                _commit_call("c1", "//*[@id='target']", confidence=0.88, reason="testid present"),
            ]
        )
    ])
    explorer = AgenticMCPExplorer(llm)
    service = HealingService(builder=None)
    ctx = _FakeContext(_ScriptedAdapter(), explorer)
    out = await service._mcp_explore_candidates(ctx, _build_input(), None)
    assert len(out) == 1
    cand = out[0]
    assert cand.strategy_id == "mcp_explore"
    assert cand.stage == "mcp_explore"
    assert cand.locator.value == "//*[@id='target']"
    assert cand.score == 0.88
    assert cand.details["source"] == "mcp_agent"
    assert cand.details["mcp_confidence"] == 0.88
    assert cand.details["mcp_reason"] == "testid present"
    assert cand.details["rounds"] == 1
    # The internal _mcp_* options must be stripped from the cleaned spec
    # (they live on the CandidateSpec.details instead).
    assert "_mcp_confidence" not in cand.locator.options
    assert "_mcp_reason" not in cand.locator.options


@pytest.mark.asyncio
async def test_mcp_explore_candidates_returns_empty_when_no_explorer() -> None:
    service = HealingService(builder=None)

    class _NoMCPCtx:
        adapter = _ScriptedAdapter()
        mcp_assist = None

        import logging
        logger = logging.getLogger("test")

    out = await service._mcp_explore_candidates(_NoMCPCtx(), _build_input(), None)
    assert out == []


@pytest.mark.asyncio
async def test_mcp_explore_candidates_swallows_explorer_exceptions() -> None:
    class _BoomExplorer:
        async def explore(self, adapter, page, inp, existing_meta):
            raise RuntimeError("network down")

    service = HealingService(builder=None)
    ctx = _FakeContext(_ScriptedAdapter(), _BoomExplorer())  # type: ignore[arg-type]
    out = await service._mcp_explore_candidates(ctx, _build_input(), None)
    assert out == []
