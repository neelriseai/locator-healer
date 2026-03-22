"""Checkbox/radio icon resolver anchored by adjacent label text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators
from xpath_healer.utils.text import normalize_text

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class CheckboxIconByLabelStrategy(Strategy):
    id = "checkbox_icon_by_label"
    priority = 135
    stage = "rules"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        return normalize_text(field_type) in {"checkbox", "radio"} and bool(
            vars_map.get("label") or vars_map.get("label_text") or vars_map.get("text")
        )

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        label = inp.intent.label or inp.vars.get("label") or inp.vars.get("label_text") or inp.intent.text
        if not label:
            return []

        escaped = label.replace("'", "\\'")
        lower = escaped.casefold()
        class_token = "radio" if normalize_text(inp.field_type) == "radio" else "checkbox"

        candidates = [
            # Label text sibling/neighbor icon.
            LocatorSpec(
                kind="xpath",
                value=(
                    f"//*[self::span or self::label][normalize-space()='{escaped}' or "
                    f"contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{lower}')]"
                    f"/preceding::*[contains(@class,'{class_token}')][1]"
                ),
            ),
            # Ancestor container lookup.
            LocatorSpec(
                kind="xpath",
                value=(
                    f"//*[self::span or self::label][normalize-space()='{escaped}' or "
                    f"contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{lower}')]"
                    f"/ancestor::*[self::label or self::li or self::div][1]//*[contains(@class,'{class_token}')][1]"
                ),
            ),
            # Demo-QA like tree-view title class.
            LocatorSpec(
                kind="xpath",
                value=(
                    f"//*[contains(@class,'rct-title') and (normalize-space()='{escaped}' or "
                    f"contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{lower}'))]"
                    f"/ancestor::*[contains(@class,'rct-text')][1]//*[contains(@class,'rct-checkbox')][1]"
                ),
            ),
        ]
        return dedupe_locators(candidates)

