"""Label + axis hint resolver strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators
from xpath_healer.utils.text import normalize_text

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class AxisHintFieldResolverStrategy(Strategy):
    id = "axis_hint_field"
    priority = 120
    stage = "rules"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        label = vars_map.get("label") or vars_map.get("label_text")
        return bool(label)

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        label = inp.intent.label or inp.vars.get("label") or inp.vars.get("label_text")
        if not label:
            return []

        axis = normalize_text(inp.intent.axis_hint or "following")
        field_type = normalize_text(inp.field_type)
        label_expr = self._label_expr(label)
        grid_exclusion = "not(ancestor::*[@role='grid' or contains(@class,'grid')])"
        candidates: list[LocatorSpec] = []

        if field_type in {"textbox", "input"}:
            if axis in {"preceding", "left", "above"}:
                path = f"{label_expr}/preceding::input[{grid_exclusion}][1]"
            else:
                path = f"{label_expr}/following::input[{grid_exclusion}][1]"
            candidates.append(LocatorSpec(kind="xpath", value=path))
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"{label_expr}/following::textarea[{grid_exclusion}][1]",
                )
            )

        if field_type in {"dropdown", "combobox"}:
            axis_name = "preceding" if axis in {"preceding", "left", "above"} else "following"
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"{label_expr}/{axis_name}::*[(self::select or self::input or @role='combobox') and {grid_exclusion}][1]",
                )
            )

        if field_type in {"checkbox", "radio"}:
            input_type = field_type
            axis_name = "preceding" if axis in {"preceding", "left", "above"} else "following"
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"{label_expr}/{axis_name}::input[@type='{input_type}' and {grid_exclusion}][1]",
                )
            )

        return dedupe_locators(candidates)

    @staticmethod
    def _label_expr(label: str) -> str:
        escaped = label.replace("'", "\\'")
        return (
            "//label[normalize-space()="
            f"'{escaped}' or contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            f"'abcdefghijklmnopqrstuvwxyz'), '{escaped.casefold()}')]"
        )

