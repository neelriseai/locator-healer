"""Button/link text ranking strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class ButtonTextCandidateStrategy(Strategy):
    id = "button_text_candidate"
    priority = 140
    stage = "rules"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        text = vars_map.get("text") or vars_map.get("button_text") or vars_map.get("label")
        return field_type.lower() in {"button", "link"} and bool(text)

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        text = inp.intent.text or inp.vars.get("text") or inp.vars.get("button_text") or inp.intent.label
        if not text:
            return []
        escaped = text.replace("'", "\\'")
        candidates: list[LocatorSpec] = []

        if inp.field_type.lower() == "button":
            candidates.extend(
                [
                    LocatorSpec(kind="role", value="button", options={"name": text, "exact": True}),
                    LocatorSpec(kind="role", value="button", options={"name": text, "exact": False}),
                    LocatorSpec(
                        kind="xpath",
                        value=f"//button[normalize-space()='{escaped}' or @value='{escaped}']",
                    ),
                    LocatorSpec(
                        kind="xpath",
                        value=(
                            f"//input[(@type='submit' or @type='button') and "
                            f"(@value='{escaped}' or contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
                            f"'{escaped.casefold()}'))]"
                        ),
                    ),
                    LocatorSpec(kind="text", value=text, options={"exact": True}),
                ]
            )
        else:
            candidates.extend(
                [
                    LocatorSpec(kind="role", value="link", options={"name": text, "exact": True}),
                    LocatorSpec(kind="role", value="link", options={"name": text, "exact": False}),
                    LocatorSpec(
                        kind="xpath",
                        value=f"//a[normalize-space()='{escaped}' or contains(normalize-space(), '{escaped}')]",
                    ),
                    LocatorSpec(kind="text", value=text, options={"exact": True}),
                ]
            )

        return dedupe_locators(candidates)

