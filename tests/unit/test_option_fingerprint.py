"""Tests for Phase 2: ElementSignature option_set, GraphContainerGrounder,
and the healing_service ``option_fingerprint`` stage.

The DOM-level interactions are exercised via lightweight in-memory fakes
that implement the subset of the RuntimeLocator API the production code
calls. The point is to validate the algorithm — round-trip serialization,
narrowest-container heuristic, option-set scoring, and pipeline wiring —
not the real Playwright/Selenium behaviour (covered by integration
tests).
"""

from __future__ import annotations

from typing import Any

import pytest

from xpath_healer.core.graph_container import GraphContainerGrounder, GroundedContainer
from xpath_healer.core.healing_service import HealingService
from xpath_healer.core.models import (
    BuildInput,
    ElementMeta,
    ElementSignature,
    Intent,
    LocatorSpec,
)


# ---------------------------------------------------------------------------
# ElementSignature serialization round-trip
# ---------------------------------------------------------------------------


def test_element_signature_round_trip_includes_option_set_and_lca() -> None:
    sig = ElementSignature(
        tag="select",
        stable_attrs={"name": "country"},
        short_text="country",
        container_path=["role:form"],
        option_set={"values": ["us", "ca"], "texts": ["United States", "Canada"]},
        container_lca_path=["testid:billing", "role:form"],
    )
    payload = sig.to_dict()
    assert payload["option_set"] == {"values": ["us", "ca"], "texts": ["United States", "Canada"]}
    assert payload["container_lca_path"] == ["testid:billing", "role:form"]
    revived = ElementSignature.from_dict(payload)
    assert revived.option_set == sig.option_set
    assert revived.container_lca_path == sig.container_lca_path


def test_element_signature_legacy_payload_hydrates_with_empty_defaults() -> None:
    # A row persisted before Phase 2 has no option_set / container_lca_path.
    legacy = {
        "tag": "input",
        "stable_attrs": {"name": "email"},
        "short_text": "email",
        "container_path": [],
        "component_kind": None,
    }
    sig = ElementSignature.from_dict(legacy)
    assert sig.option_set == {}
    assert sig.container_lca_path == []


# ---------------------------------------------------------------------------
# Fake adapter + page for grounder / scorer tests
# ---------------------------------------------------------------------------


class _ScriptedLocator:
    """Locator that returns whatever the test scripted, regardless of selector."""

    def __init__(self, page: "_ScriptedPage", payload_for_evaluate: Any | Exception) -> None:
        self._page = page
        self._payload = payload_for_evaluate

    async def count(self) -> int:
        return self._page.candidate_count_for_root

    def nth(self, idx: int) -> "_ScriptedLocator":
        return self

    @property
    def first(self) -> "_ScriptedLocator":
        return self

    async def is_visible(self) -> bool:
        return True

    async def is_enabled(self) -> bool:
        return True

    async def bounding_box(self) -> dict[str, float] | None:
        return {"x": 0.0, "y": 0.0, "width": 100.0, "height": 20.0}

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _ScriptedAdapter:
    name = "scripted"

    def __init__(self, page: "_ScriptedPage") -> None:
        self._page = page

    async def resolve_locator(self, root: Any, locator_spec: LocatorSpec) -> _ScriptedLocator:
        # Grounder calls resolve_locator(":root") first; then the scorer
        # resolves the container_xpath. We return whatever the page has
        # queued up next.
        return _ScriptedLocator(self._page, self._page._next_payload())

    async def capture_page_html(self, page: Any) -> str:
        return self._page.html


class _ScriptedPage:
    """Bookkeeping for what the next evaluate() call should return."""

    def __init__(self, html: str = "<html></html>") -> None:
        self.html = html
        self.candidate_count_for_root = 1
        self._queue: list[Any | Exception] = []

    def queue(self, payload: Any) -> None:
        self._queue.append(payload)

    def _next_payload(self) -> Any | Exception:
        if not self._queue:
            return None
        return self._queue.pop(0)


# ---------------------------------------------------------------------------
# GraphContainerGrounder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grounder_returns_ok_when_payload_indicates_match() -> None:
    page = _ScriptedPage()
    page.queue(
        {
            "ok": True,
            "anchor_text": "country",
            "container_xpath": "//*[@data-testid='billing']",
            "container_token": "testid:billing",
            "container_path": ["testid:billing"],
            "candidate_count": 3,
            "ancestors": [],
        }
    )
    grounder = GraphContainerGrounder(_ScriptedAdapter(page))
    result = await grounder.ground(page, anchor_text="Country", field_type="dropdown")
    assert result.ok is True
    assert result.xpath == "//*[@data-testid='billing']"
    assert result.path == ["testid:billing"]
    assert result.candidate_count == 3
    assert result.details["container_token"] == "testid:billing"


@pytest.mark.asyncio
async def test_grounder_returns_failure_for_empty_anchor() -> None:
    page = _ScriptedPage()
    grounder = GraphContainerGrounder(_ScriptedAdapter(page))
    result = await grounder.ground(page, anchor_text="", field_type="dropdown")
    assert result.ok is False
    assert result.details["reason"] == "no_anchor_text"


@pytest.mark.asyncio
async def test_grounder_returns_failure_when_payload_not_ok() -> None:
    page = _ScriptedPage()
    page.queue({"ok": False, "reason": "anchor_not_found"})
    grounder = GraphContainerGrounder(_ScriptedAdapter(page))
    result = await grounder.ground(page, anchor_text="Nonexistent", field_type="dropdown")
    assert result.ok is False
    assert result.details["reason"] == "anchor_not_found"


@pytest.mark.asyncio
async def test_grounder_swallows_evaluate_exception() -> None:
    page = _ScriptedPage()
    page.queue(RuntimeError("DOM gone"))
    grounder = GraphContainerGrounder(_ScriptedAdapter(page))
    result = await grounder.ground(page, anchor_text="Country", field_type="dropdown")
    assert result.ok is False
    assert result.details["reason"] == "evaluate_failed"


# ---------------------------------------------------------------------------
# _option_fingerprint_candidates stage
# ---------------------------------------------------------------------------


def _build_input(
    *,
    label: str = "Region",
    field_type: str = "dropdown",
) -> BuildInput:
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


def _meta_with_option_set(option_set: dict[str, Any]) -> ElementMeta:
    return ElementMeta(
        app_id="app",
        page_name="checkout",
        element_name="country_select",
        field_type="dropdown",
        signature=ElementSignature(
            tag="select",
            stable_attrs={"name": "country"},
            short_text="country",
            option_set=option_set,
            container_lca_path=["testid:billing"],
        ),
    )


class _FakeContext:
    """Minimal StrategyContext-shaped stub for the stage method."""

    def __init__(self, adapter: _ScriptedAdapter) -> None:
        self.adapter = adapter


@pytest.mark.asyncio
async def test_option_fingerprint_returns_empty_without_prior_option_set() -> None:
    service = HealingService(builder=None)  # builder is unused for this method.
    page = _ScriptedPage()
    ctx = _FakeContext(_ScriptedAdapter(page))
    inp = _build_input()
    meta_no_options = ElementMeta(
        app_id="app",
        page_name="checkout",
        element_name="country_select",
        field_type="dropdown",
        signature=ElementSignature(tag="select"),
    )
    out = await service._option_fingerprint_candidates(ctx, inp, meta_no_options)
    assert out == []


@pytest.mark.asyncio
async def test_option_fingerprint_returns_empty_without_anchor_text() -> None:
    service = HealingService(builder=None)
    page = _ScriptedPage()
    ctx = _FakeContext(_ScriptedAdapter(page))
    inp = BuildInput(
        page=object(),
        app_id="app",
        page_name="checkout",
        element_name="country_select",
        field_type="dropdown",
        fallback=LocatorSpec(kind="xpath", value="//missing"),
        vars={},
        intent=Intent(),
    )
    meta = _meta_with_option_set({"values": ["us", "ca"]})
    # Wipe short_text too so no anchor can be inferred.
    meta.signature.short_text = ""
    out = await service._option_fingerprint_candidates(ctx, inp, meta)
    assert out == []


@pytest.mark.asyncio
async def test_option_fingerprint_emits_ranked_candidates_when_container_found() -> None:
    service = HealingService(builder=None)
    page = _ScriptedPage()
    # 1st evaluate: grounder finds the container.
    page.queue(
        {
            "ok": True,
            "anchor_text": "region",
            "container_xpath": "//*[@data-testid='billing']",
            "container_token": "testid:billing",
            "container_path": ["testid:billing"],
            "candidate_count": 2,
            "ancestors": [],
        }
    )
    # 2nd evaluate: scorer returns two candidates, highest first.
    page.queue(
        [
            {"xpath": "//*[@id='country-new']", "score": 0.92, "breakdown": {"value_jaccard": 1.0}, "tag": "select"},
            {"xpath": "//*[@id='other']", "score": 0.30, "breakdown": {"value_jaccard": 0.1}, "tag": "select"},
        ]
    )
    ctx = _FakeContext(_ScriptedAdapter(page))
    inp = _build_input(label="Region")
    meta = _meta_with_option_set(
        {"values": ["us", "ca"], "texts": ["United States", "Canada"]}
    )
    out = await service._option_fingerprint_candidates(ctx, inp, meta)

    # Both candidates kept (0.92 ≥ 0.55) but the weak one is below the
    # 0.55 floor so only the strong one survives.
    assert len(out) == 1
    chosen = out[0]
    assert chosen.strategy_id == "option_fingerprint"
    assert chosen.stage == "option_fingerprint"
    assert chosen.locator.value == "//*[@id='country-new']"
    assert chosen.score == 0.92
    assert chosen.details["container_xpath"] == "//*[@data-testid='billing']"
    assert chosen.details["container_path"] == ["testid:billing"]
    assert chosen.details["anchor_text"] == "Region"


@pytest.mark.asyncio
async def test_option_fingerprint_drops_all_below_min_score() -> None:
    service = HealingService(builder=None)
    page = _ScriptedPage()
    page.queue(
        {
            "ok": True,
            "anchor_text": "region",
            "container_xpath": "//*[@data-testid='billing']",
            "container_token": "testid:billing",
            "container_path": ["testid:billing"],
            "candidate_count": 1,
            "ancestors": [],
        }
    )
    page.queue([{"xpath": "//*[@id='weak']", "score": 0.4, "breakdown": {}, "tag": "select"}])
    ctx = _FakeContext(_ScriptedAdapter(page))
    inp = _build_input()
    meta = _meta_with_option_set({"values": ["us", "ca"]})
    out = await service._option_fingerprint_candidates(ctx, inp, meta)
    assert out == []


@pytest.mark.asyncio
async def test_option_fingerprint_returns_empty_when_grounder_fails() -> None:
    service = HealingService(builder=None)
    page = _ScriptedPage()
    page.queue({"ok": False, "reason": "anchor_not_found"})
    ctx = _FakeContext(_ScriptedAdapter(page))
    inp = _build_input()
    meta = _meta_with_option_set({"values": ["us", "ca"]})
    out = await service._option_fingerprint_candidates(ctx, inp, meta)
    assert out == []
