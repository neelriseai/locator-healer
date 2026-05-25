"""Anchor-text-driven bidirectional field resolver.

Replaces the hard directional assumption of `AxisHintFieldResolverStrategy`
for textbox/dropdown intents. From the anchor label this strategy emits
candidates in BOTH preceding and following axes (plus container-scoped
lookups and ``label[@for]``), so a layout change that flips the label
from above to beside the field still heals.

When ``Intent.axis_hint`` is supplied it is honoured as a *soft*
tie-breaker only: the hinted direction's candidates are emitted first so
the validator tries them first, but the opposite direction is always
included. Existing scripts that still pass ``axisHint`` therefore keep
their previous resolution order while gaining bidirectional fallback.

For checkbox/radio bidirectional coverage is already provided by
``LabelProximityInteractableStrategy``; this strategy intentionally fills
the textbox/dropdown gap and does not duplicate that work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators
from xpath_healer.utils.text import normalize_text

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


# Deterministic mapping from label/name keywords to expected HTML input
# subtypes. Keyword matching is substring on the lower-cased label. The
# values are tried in declared order; an unspecified `input` is always
# emitted last as a generic fallback.
_INTENT_SUBTYPE_KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("email", "e-mail"), ("email",)),
    (("password", "passwd", "pwd"), ("password",)),
    (("phone", "mobile", "tel", "contact number"), ("tel",)),
    (("date of birth", "dob", "birthdate", "birth date", " date"), ("date",)),
    (("amount", "qty", "quantity", "count", "age", "number"), ("number",)),
    (("website", "url", "link"), ("url",)),
    (("search",), ("search",)),
)

_PRECEDING_HINTS = {"preceding", "left", "above", "before", "up", "previous"}


def _resolve_input_subtypes(label: str | None) -> list[str]:
    """Return preferred input @type values for the given label, in order."""
    lowered = (label or "").casefold()
    matched: list[str] = []
    for keywords, subtypes in _INTENT_SUBTYPE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            for sub in subtypes:
                if sub not in matched:
                    matched.append(sub)
    return matched


class BidirectionalAnchorFieldStrategy(Strategy):
    """Emit field candidates on both sides of the anchor label.

    Priority is set lower than :class:`AxisHintFieldResolverStrategy` so
    these candidates are evaluated first. Axis-hint remains registered as
    a safety net for cases this strategy does not cover.
    """

    id = "bidirectional_anchor_field"
    priority = 115
    stage = "rules"

    # Field types this strategy is responsible for. checkbox/radio are
    # deliberately omitted — LabelProximityInteractableStrategy already
    # emits bidirectional candidates for those.
    _SUPPORTED_FIELDS = {"textbox", "input", "dropdown", "combobox"}

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        if normalize_text(field_type) not in self._SUPPORTED_FIELDS:
            return False
        label = vars_map.get("label") or vars_map.get("label_text") or vars_map.get("name")
        return bool(label)

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        label = (
            inp.intent.label
            or inp.vars.get("label")
            or inp.vars.get("label_text")
            or inp.vars.get("name")
        )
        if not label:
            return []

        field_type = normalize_text(inp.field_type)
        axis_hint = normalize_text(inp.intent.axis_hint or inp.vars.get("axis_hint") or "")
        prefer_preceding = axis_hint in _PRECEDING_HINTS

        label_expr = self._label_expr(label)
        # Limit container lookups to common form-row ancestors to avoid
        # walking the whole document on deeply nested pages.
        nearest_container = (
            f"{label_expr}/ancestor::*[self::label or self::div or self::section "
            "or self::form or self::fieldset or self::li or self::tr][1]"
        )
        grid_exclusion = "not(ancestor::*[@role='grid' or contains(@class,'grid')])"

        if field_type in {"textbox", "input"}:
            return dedupe_locators(
                self._textbox_candidates(
                    label_expr=label_expr,
                    nearest_container=nearest_container,
                    grid_exclusion=grid_exclusion,
                    subtypes=_resolve_input_subtypes(label),
                    prefer_preceding=prefer_preceding,
                )
            )

        if field_type in {"dropdown", "combobox"}:
            return dedupe_locators(
                self._dropdown_candidates(
                    label_expr=label_expr,
                    nearest_container=nearest_container,
                    grid_exclusion=grid_exclusion,
                    prefer_preceding=prefer_preceding,
                )
            )

        return []

    # ------------------------------------------------------------------
    # Candidate builders
    # ------------------------------------------------------------------

    def _textbox_candidates(
        self,
        *,
        label_expr: str,
        nearest_container: str,
        grid_exclusion: str,
        subtypes: list[str],
        prefer_preceding: bool,
    ) -> list[LocatorSpec]:
        candidates: list[LocatorSpec] = []

        # 1) label[@for]=input[@id] — strongest deterministic association.
        for sub in subtypes:
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=(
                        f"//input[@id = ({label_expr}/@for)[1] and @type='{sub}']"
                    ),
                )
            )
        candidates.append(
            LocatorSpec(
                kind="xpath",
                value=f"//input[@id = ({label_expr}/@for)[1]]",
            )
        )
        # textarea also legitimately satisfies a textbox intent.
        candidates.append(
            LocatorSpec(
                kind="xpath",
                value=f"//textarea[@id = ({label_expr}/@for)[1]]",
            )
        )

        # 2) Container-scoped lookup — input inside the same row as the
        # label, regardless of direction. Add subtyped first, generic
        # after.
        for sub in subtypes:
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=(
                        f"{nearest_container}//input[@type='{sub}' and {grid_exclusion}][1]"
                    ),
                )
            )
        candidates.append(
            LocatorSpec(
                kind="xpath",
                value=f"{nearest_container}//input[{grid_exclusion}][1]",
            )
        )
        candidates.append(
            LocatorSpec(
                kind="xpath",
                value=f"{nearest_container}//textarea[{grid_exclusion}][1]",
            )
        )

        # 3) Sibling axes — both directions. Honour axis_hint by
        # ordering the hinted direction first.
        primary_axis = "preceding" if prefer_preceding else "following"
        secondary_axis = "following" if prefer_preceding else "preceding"

        for axis in (primary_axis, secondary_axis):
            for sub in subtypes:
                candidates.append(
                    LocatorSpec(
                        kind="xpath",
                        value=(
                            f"{label_expr}/{axis}::input[@type='{sub}' and {grid_exclusion}][1]"
                        ),
                    )
                )
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"{label_expr}/{axis}::input[{grid_exclusion}][1]",
                )
            )
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"{label_expr}/{axis}::textarea[{grid_exclusion}][1]",
                )
            )

        return candidates

    def _dropdown_candidates(
        self,
        *,
        label_expr: str,
        nearest_container: str,
        grid_exclusion: str,
        prefer_preceding: bool,
    ) -> list[LocatorSpec]:
        # Both native <select> and ARIA combobox patterns are accepted.
        combobox_pred = (
            "(self::select or @role='combobox' or "
            "(self::input and (@role='combobox' or @aria-haspopup='listbox'))) "
            f"and {grid_exclusion}"
        )
        candidates: list[LocatorSpec] = []

        # 1) label[@for] association.
        candidates.append(
            LocatorSpec(
                kind="xpath",
                value=f"//select[@id = ({label_expr}/@for)[1]]",
            )
        )
        candidates.append(
            LocatorSpec(
                kind="xpath",
                value=(
                    f"//*[@id = ({label_expr}/@for)[1] and "
                    "(@role='combobox' or @aria-haspopup='listbox')]"
                ),
            )
        )

        # 2) Container-scoped.
        candidates.append(
            LocatorSpec(
                kind="xpath",
                value=f"{nearest_container}//*[{combobox_pred}][1]",
            )
        )

        # 3) Sibling axes — both directions, axis_hint sets order.
        primary_axis = "preceding" if prefer_preceding else "following"
        secondary_axis = "following" if prefer_preceding else "preceding"
        for axis in (primary_axis, secondary_axis):
            candidates.append(
                LocatorSpec(
                    kind="xpath",
                    value=f"{label_expr}/{axis}::*[{combobox_pred}][1]",
                )
            )

        return candidates

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _label_expr(label: str) -> str:
        """Case-insensitive label match XPath, mirroring axis_hint_field."""
        escaped = label.replace("'", "\\'")
        lower = escaped.casefold()
        return (
            "//*[(self::label or self::span) and ("
            f"normalize-space()='{escaped}' or "
            "contains(translate(normalize-space(),"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
            "'abcdefghijklmnopqrstuvwxyz'),"
            f"'{lower}'))]"
        )
