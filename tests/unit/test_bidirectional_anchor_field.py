"""Unit tests for BidirectionalAnchorFieldStrategy.

These tests do not need a live browser — they verify that the strategy
emits the expected candidate XPaths (both directions, intent-subtype
predicates, label[@for] association) and that axis_hint is honoured as
a soft tie-breaker (ordering only, never exclusion).
"""

from __future__ import annotations

import pytest

from xpath_healer.core.context import StrategyContext
from xpath_healer.core.models import BuildInput, Intent, LocatorSpec
from xpath_healer.core.strategies.bidirectional_anchor_field import (
    BidirectionalAnchorFieldStrategy,
)


def _make_input(
    field_type: str,
    label: str,
    *,
    axis_hint: str | None = None,
    extra_vars: dict[str, str] | None = None,
) -> BuildInput:
    vars_map: dict[str, str] = {"label": label}
    if extra_vars:
        vars_map.update(extra_vars)
    return BuildInput(
        page=None,
        app_id="app",
        page_name="page",
        element_name="el",
        field_type=field_type,
        fallback=LocatorSpec(kind="css", value="*"),
        vars=vars_map,
        intent=Intent(label=label, axis_hint=axis_hint),
    )


def _values(candidates: list[LocatorSpec]) -> list[str]:
    return [c.value for c in candidates]


def test_supports_textbox_and_dropdown_only() -> None:
    strat = BidirectionalAnchorFieldStrategy()
    assert strat.supports("textbox", {"label": "Email"})
    assert strat.supports("input", {"label": "Email"})
    assert strat.supports("dropdown", {"label": "Country"})
    assert strat.supports("combobox", {"label": "Country"})
    # checkbox/radio handled by LabelProximityInteractableStrategy
    assert not strat.supports("checkbox", {"label": "Accept"})
    assert not strat.supports("radio", {"label": "Male"})
    # No label → no support
    assert not strat.supports("textbox", {})


@pytest.mark.asyncio
async def test_textbox_emits_both_directions(
    simple_context: StrategyContext,
) -> None:
    strat = BidirectionalAnchorFieldStrategy()
    inp = _make_input("textbox", "Full Name")
    out = await strat.build(simple_context, inp)
    values = _values(out)

    # both directions present
    assert any("/preceding::input[" in v for v in values), values
    assert any("/following::input[" in v for v in values), values
    # textarea fallback present
    assert any("/preceding::textarea[" in v for v in values), values
    assert any("/following::textarea[" in v for v in values), values
    # label[@for] association present
    assert any("@id = (" in v and "/@for)[1]" in v for v in values), values


@pytest.mark.asyncio
async def test_textbox_axis_hint_orders_preceding_first(
    simple_context: StrategyContext,
) -> None:
    strat = BidirectionalAnchorFieldStrategy()
    inp = _make_input("textbox", "Full Name", axis_hint="preceding")
    out = await strat.build(simple_context, inp)
    values = _values(out)

    first_preceding = next(
        (i for i, v in enumerate(values) if "/preceding::input[" in v), None
    )
    first_following = next(
        (i for i, v in enumerate(values) if "/following::input[" in v), None
    )
    assert first_preceding is not None and first_following is not None
    assert first_preceding < first_following, (
        "axis_hint='preceding' should order preceding-axis candidates first"
    )


@pytest.mark.asyncio
async def test_textbox_no_axis_hint_orders_following_first(
    simple_context: StrategyContext,
) -> None:
    strat = BidirectionalAnchorFieldStrategy()
    inp = _make_input("textbox", "Full Name")
    out = await strat.build(simple_context, inp)
    values = _values(out)

    first_preceding = next(
        (i for i, v in enumerate(values) if "/preceding::input[" in v), None
    )
    first_following = next(
        (i for i, v in enumerate(values) if "/following::input[" in v), None
    )
    assert first_preceding is not None and first_following is not None
    assert first_following < first_preceding


@pytest.mark.asyncio
async def test_email_label_emits_type_email_predicate(
    simple_context: StrategyContext,
) -> None:
    strat = BidirectionalAnchorFieldStrategy()
    inp = _make_input("textbox", "Email Address")
    out = await strat.build(simple_context, inp)
    values = _values(out)
    assert any("@type='email'" in v for v in values), values


@pytest.mark.asyncio
async def test_dob_label_emits_type_date_predicate(
    simple_context: StrategyContext,
) -> None:
    strat = BidirectionalAnchorFieldStrategy()
    inp = _make_input("textbox", "Date of Birth")
    out = await strat.build(simple_context, inp)
    values = _values(out)
    assert any("@type='date'" in v for v in values), values


@pytest.mark.asyncio
async def test_dropdown_emits_select_and_combobox_candidates(
    simple_context: StrategyContext,
) -> None:
    strat = BidirectionalAnchorFieldStrategy()
    inp = _make_input("dropdown", "Country")
    out = await strat.build(simple_context, inp)
    values = _values(out)

    assert any("self::select" in v for v in values), values
    assert any("@role='combobox'" in v for v in values), values
    # Both directions covered for dropdowns too
    assert any("/preceding::*[" in v for v in values), values
    assert any("/following::*[" in v for v in values), values
    # label[@for] association for select present
    assert any("//select[@id = (" in v for v in values), values


@pytest.mark.asyncio
async def test_unknown_field_type_returns_empty(
    simple_context: StrategyContext,
) -> None:
    strat = BidirectionalAnchorFieldStrategy()
    inp = _make_input("button", "Submit")
    out = await strat.build(simple_context, inp)
    assert out == []
