"""Composite dropdown control resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class CompositeLabelControlStrategy(Strategy):
    id = "composite_label_control"
    priority = 130
    stage = "rules"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        return field_type.lower() in {"dropdown", "combobox"} and bool(
            vars_map.get("label") or vars_map.get("label_text")
        )

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        label = inp.intent.label or inp.vars.get("label") or inp.vars.get("label_text")
        if not label:
            return []
        escaped = label.replace("'", "\\'")
        label_expr = f"//label[normalize-space()='{escaped}']"
        grid_exclusion = "not(ancestor::*[@role='grid' or contains(@class,'grid')])"
        candidates = [
            LocatorSpec(
                kind="xpath",
                value=(
                    f"{label_expr}/following::*[self::div or self::span][1]"
                    f"//*[self::input or self::select or @role='combobox'][{grid_exclusion}][1]"
                ),
            ),
            LocatorSpec(
                kind="xpath",
                value=(
                    f"{label_expr}/following::*[(self::input or self::select or @role='combobox') and "
                    f"{grid_exclusion}][1]"
                ),
            ),
            LocatorSpec(
                kind="xpath",
                value=(
                    f"{label_expr}/following::*[self::div or self::span][1]"
                    f"//*[self::svg and {grid_exclusion}]/preceding::*[self::input or @role='combobox'][1]"
                ),
            ),
        ]
        return dedupe_locators(candidates)

