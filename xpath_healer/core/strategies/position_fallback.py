"""Final positional fallback strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy
from xpath_healer.utils.text import normalize_text

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class PositionFallbackStrategy(Strategy):
    id = "position_fallback"
    priority = 900
    stage = "position"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        return True

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        allow = ctx.config.allow_position_fallback or inp.intent.allow_position
        if inp.hints and inp.hints.allow_position_fallback:
            allow = True
        if not allow:
            return []

        field = normalize_text(inp.field_type)
        index = max(inp.intent.occurrence, 0)
        selector = "*"
        if field in {"button"}:
            selector = "button,input[type='submit'],input[type='button']"
        elif field in {"textbox", "input"}:
            selector = "input,textarea"
        elif field in {"dropdown", "combobox"}:
            selector = "select,[role='combobox'],input[aria-haspopup]"
        elif field in {"link"}:
            selector = "a"
        elif field in {"checkbox"}:
            selector = "input[type='checkbox'],[role='checkbox']"
        elif field in {"radio"}:
            selector = "input[type='radio'],[role='radio']"
        elif field in {"gridcell", "grid_header", "gridheader", "columnheader"}:
            selector = "[role='gridcell'],[role='columnheader'],[col-id]"

        scope = None
        scope_value = inp.vars.get("container_selector")
        if scope_value:
            scope = LocatorSpec(kind="css", value=scope_value)

        return [LocatorSpec(kind="css", value=selector, options={"nth": index}, scope=scope)]

