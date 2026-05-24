"""Label-anchored proximity resolver for nearby interactable controls.

Search order intentionally prefers nearest structural relations:
1) child/descendant of label
2) preceding/following sibling-ish controls
3) nearest parent container
4) ancestor container
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators
from xpath_healer.utils.text import normalize_text

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class LabelProximityInteractableStrategy(Strategy):
    id = "label_proximity_interactable"
    priority = 132
    stage = "rules"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        field_type_norm = normalize_text(field_type)
        if field_type_norm not in {"button", "checkbox", "radio"}:
            return False
        label = vars_map.get("label") or vars_map.get("label_text") or vars_map.get("text")
        return bool(label)

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        field_type_norm = normalize_text(inp.field_type)
        label = inp.intent.label or inp.vars.get("label") or inp.vars.get("label_text") or inp.vars.get("text")
        if not label:
            return []

        escaped = label.replace("'", "\\'")
        lower = escaped.casefold()
        label_match = (
            f"normalize-space()='{escaped}' or "
            f"contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{lower}')"
        )
        label_expr = f"//*[self::label or self::span][{label_match}]"
        nearest_container = f"{label_expr}/ancestor::*[self::label or self::li or self::div][1]"
        ancestor_container = f"{label_expr}/ancestor::*[self::li or self::div][2]"
        candidates: list[LocatorSpec] = []

        if field_type_norm == "button":
            target = normalize_text(inp.vars.get("target"))
            if target in {"toggle", "expand", "collapse"}:
                control_pred = (
                    "self::button and ("
                    "contains(@class,'toggle') or "
                    "contains(@class,'expand') or "
                    "contains(@class,'collapse') or "
                    "contains(@class,'rct-') or "
                    "contains(translate(normalize-space(@aria-label),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'toggle') or "
                    "contains(translate(normalize-space(@aria-label),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'expand') or "
                    "contains(translate(normalize-space(@aria-label),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'collapse')"
                    ")"
                )
            else:
                control_pred = (
                    "self::button or @role='button' or "
                    "(self::input and (@type='button' or @type='submit'))"
                )

            candidates.extend(
                [
                    LocatorSpec(kind="xpath", value=f"{label_expr}//*[{control_pred}][1]"),
                    LocatorSpec(kind="xpath", value=f"{label_expr}/preceding::*[{control_pred}][1]"),
                    LocatorSpec(kind="xpath", value=f"{label_expr}/following::*[{control_pred}][1]"),
                    LocatorSpec(kind="xpath", value=f"{nearest_container}//*[{control_pred}][1]"),
                    LocatorSpec(kind="xpath", value=f"{ancestor_container}//*[{control_pred}][1]"),
                ]
            )
            return dedupe_locators(candidates)

        input_type = field_type_norm
        proxy_class = "checkbox" if input_type == "checkbox" else "radio"
        candidates.extend(
            [
                LocatorSpec(
                    kind="xpath",
                    value=f"//input[@id = //label[{label_match}]/@for and @type='{input_type}'][1]",
                ),
                LocatorSpec(kind="xpath", value=f"{label_expr}//input[@type='{input_type}'][1]"),
                LocatorSpec(kind="xpath", value=f"{label_expr}/preceding::input[@type='{input_type}'][1]"),
                LocatorSpec(kind="xpath", value=f"{label_expr}/following::input[@type='{input_type}'][1]"),
                LocatorSpec(kind="xpath", value=f"{nearest_container}//input[@type='{input_type}'][1]"),
                LocatorSpec(kind="xpath", value=f"{nearest_container}//*[contains(@class,'{proxy_class}')][1]"),
                LocatorSpec(kind="xpath", value=f"{ancestor_container}//input[@type='{input_type}'][1]"),
                LocatorSpec(kind="xpath", value=f"{ancestor_container}//*[contains(@class,'{proxy_class}')][1]"),
            ]
        )
        return dedupe_locators(candidates)

