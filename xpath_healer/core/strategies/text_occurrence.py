"""Text occurrence strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators
from xpath_healer.utils.text import normalize_text

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class TextOccurrenceStrategy(Strategy):
    id = "text_occurrence"
    priority = 230
    stage = "defaults"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        has_text = bool(vars_map.get("text") or vars_map.get("label") or vars_map.get("label_text"))
        return has_text and normalize_text(field_type) in {"text", "button", "link", "label", "generic"}

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        text = inp.intent.text or inp.vars.get("text") or inp.intent.label
        if not text:
            return []
        occurrence = max(inp.intent.occurrence, 0)
        escaped = text.replace("'", "\\'")
        candidates = [
            LocatorSpec(kind="text", value=text, options={"exact": True, "nth": occurrence}),
            LocatorSpec(kind="text", value=text, options={"exact": False, "nth": occurrence}),
            LocatorSpec(
                kind="xpath",
                value=f"//*[contains(normalize-space(), '{escaped}') and not(ancestor::*[@role='grid'])]",
                options={"nth": occurrence},
            ),
        ]
        return dedupe_locators(candidates)

