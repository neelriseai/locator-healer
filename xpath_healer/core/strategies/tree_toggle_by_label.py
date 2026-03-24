"""Tree expand/collapse toggle resolver anchored by adjacent label text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators
from xpath_healer.utils.text import normalize_text

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class TreeToggleByLabelStrategy(Strategy):
    id = "tree_toggle_by_label"
    priority = 136
    stage = "rules"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        field_type_norm = normalize_text(field_type)
        if field_type_norm != "button":
            return False
        target = normalize_text(vars_map.get("target"))
        label = vars_map.get("label") or vars_map.get("label_text") or vars_map.get("text")
        return target in {"toggle", "expand", "collapse"} and bool(label)

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        label = inp.intent.label or inp.vars.get("label") or inp.vars.get("label_text") or inp.vars.get("text")
        if not label:
            return []

        escaped = label.replace("'", "\\'")
        lower = escaped.casefold()
        label_match = (
            f"normalize-space()='{escaped}' or "
            f"contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{lower}')"
        )
        toggle_button = (
            "self::button and ("
            "contains(@class,'rct-collapse-btn') or "
            "contains(@class,'rct-expand-btn') or "
            "contains(@class,'rct-parent-open') or "
            "contains(@class,'rct-parent-close') or "
            "contains(@class,'rct-icon-expand') or "
            "translate(normalize-space(@aria-label),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='toggle' or "
            "contains(translate(normalize-space(@aria-label),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'expand') or "
            "contains(translate(normalize-space(@aria-label),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'collapse')"
            ")"
        )

        candidates = [
            LocatorSpec(
                kind="xpath",
                value=(
                    f"//*[contains(@class,'rct-title') and ({label_match})]"
                    f"/ancestor::*[contains(@class,'rct-text')][1]//*[{toggle_button}][1]"
                ),
            ),
            LocatorSpec(
                kind="xpath",
                value=(
                    f"//*[self::span or self::label][{label_match}]"
                    f"/ancestor::li[1]//*[{toggle_button}][1]"
                ),
            ),
            LocatorSpec(
                kind="xpath",
                value=(
                    f"//*[self::span or self::label][{label_match}]"
                    f"/preceding::button[contains(@class,'rct-collapse-btn') or contains(@class,'rct-expand-btn')][1]"
                ),
            ),
        ]
        return dedupe_locators(candidates)

