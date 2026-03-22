"""Template-driven deterministic locator generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators, safe_format

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class GenericTemplateStrategy(Strategy):
    id = "generic_template"
    priority = 100
    stage = "rules"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        return True

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        templates = ctx.template_set(inp.page_name, inp.element_name)
        candidates: list[LocatorSpec] = []
        for template in templates:
            field_types = [str(ft).lower() for ft in template.get("field_types", [])]
            if field_types and inp.field_type.lower() not in field_types:
                continue
            pattern = str(template.get("pattern") or "")
            if not pattern:
                continue
            selector = safe_format(pattern, inp.vars)
            if not selector:
                continue

            kind = str(template.get("kind") or self._infer_kind(selector)).lower()
            options = dict(template.get("options") or {})
            scope = None
            scope_payload = template.get("scope")
            if isinstance(scope_payload, dict):
                scope = LocatorSpec.from_dict(scope_payload)

            try:
                candidates.append(LocatorSpec(kind=kind, value=selector, options=options, scope=scope))
            except ValueError:
                continue
        return dedupe_locators(candidates)

    @staticmethod
    def _infer_kind(selector: str) -> str:
        text = selector.strip()
        if text.startswith("//") or text.startswith("("):
            return "xpath"
        if text.startswith("role="):
            return "pw"
        return "css"

