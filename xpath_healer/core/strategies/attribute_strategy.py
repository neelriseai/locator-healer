"""Type-aware stable attribute fallback strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators
from xpath_healer.utils.text import normalize_text

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


ATTRIBUTE_ALIASES: dict[str, list[str]] = {
    "data-testid": ["data-testid", "data_testid", "testid", "test_id"],
    "aria-label": ["aria-label", "aria_label", "label", "label_text"],
    "name": ["name", "field_name"],
    "formcontrolname": ["formcontrolname", "form_control_name"],
    "placeholder": ["placeholder", "hint"],
    "role": ["role"],
    "href": ["href", "link"],
    "col-id": ["col-id", "col_id", "column", "column_id"],
    "aria-colindex": ["aria-colindex", "aria_colindex", "colindex", "column_index"],
    "class": ["class", "class_name"],
}


class AttributeStrategy(Strategy):
    id = "attribute"
    priority = 210
    stage = "defaults"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        return bool(vars_map)

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        candidates: list[LocatorSpec] = []
        vars_map = inp.vars
        attr_priority = inp.hints.attr_priority_order if inp.hints and inp.hints.attr_priority_order else ctx.config.attribute_priority

        for attr in attr_priority:
            value = self._find_value(attr, vars_map)
            if not value:
                continue

            if attr == "role":
                candidates.append(LocatorSpec(kind="role", value=value, options={"name": inp.intent.text or inp.intent.label}))
                continue
            css = f'[{attr}="{self._css_escape(value)}"]'
            candidates.append(LocatorSpec(kind="css", value=css))

        if normalize_text(inp.field_type) in {"textbox", "input"} and inp.intent.label:
            label = inp.intent.label.replace("'", "\\'")
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"//label[normalize-space()='{label}']/following::input[1]",
                )
            )

        if normalize_text(inp.field_type) in {"link"}:
            href = self._find_value("href", vars_map)
            if href:
                candidates.append(LocatorSpec(kind="css", value=f'a[href="{self._css_escape(href)}"]'))

        return dedupe_locators(candidates)

    @staticmethod
    def _find_value(attr: str, vars_map: dict[str, str]) -> str | None:
        for key in ATTRIBUTE_ALIASES.get(attr, [attr]):
            value = vars_map.get(key)
            if value:
                return value
        return None

    @staticmethod
    def _css_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

