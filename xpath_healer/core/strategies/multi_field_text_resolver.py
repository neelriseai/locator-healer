"""Wide-net text resolver with grid exclusion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class MultiFieldTextResolverStrategy(Strategy):
    id = "multi_field_text_resolver"
    priority = 150
    stage = "rules"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        return bool(vars_map.get("text") or vars_map.get("label") or vars_map.get("label_text"))

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        label = inp.intent.label or inp.vars.get("label") or inp.vars.get("label_text")
        text = inp.intent.text or inp.vars.get("text") or label
        if not text:
            return []

        field_type = inp.field_type.lower()
        text_e = text.replace("'", "\\'")
        grid_ex = "not(ancestor::*[@role='grid' or contains(@class,'grid')])"
        candidates: list[LocatorSpec] = []

        if field_type in {"textbox", "input"} and label:
            label_e = label.replace("'", "\\'")
            candidates.extend(
                [
                    LocatorSpec(
                        kind="xpath",
                        value=f"//label[normalize-space()='{label_e}']/following::input[{grid_ex}][1]",
                    ),
                    LocatorSpec(
                        kind="xpath",
                        value=f"//label[normalize-space()='{label_e}']/following::textarea[{grid_ex}][1]",
                    ),
                    LocatorSpec(
                        kind="xpath",
                        value=(
                            f"//input[{grid_ex} and (@placeholder='{label_e}' or @aria-label='{label_e}' "
                            f"or @name='{label_e}' or @formcontrolname='{label_e}')]"
                        ),
                    ),
                ]
            )

        if field_type in {"button", "link"}:
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"//*[(self::button or self::a) and {grid_ex} and contains(normalize-space(), '{text_e}')]",
                )
            )
            candidates.append(LocatorSpec(kind="text", value=text, options={"exact": False}))

        if field_type in {"dropdown", "combobox"} and label:
            label_e = label.replace("'", "\\'")
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=(
                        f"//label[normalize-space()='{label_e}']/following::*[(self::select or @role='combobox' or "
                        f"self::input) and {grid_ex}][1]"
                    ),
                )
            )

        if field_type in {"checkbox", "radio"} and label:
            label_e = label.replace("'", "\\'")
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"//label[normalize-space()='{label_e}']/following::input[@type='{field_type}' and {grid_ex}][1]",
                )
            )

        if field_type not in {"gridcell", "grid_header", "gridheader"}:
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"//*[contains(normalize-space(), '{text_e}') and {grid_ex}]",
                )
            )

        return dedupe_locators(candidates)
