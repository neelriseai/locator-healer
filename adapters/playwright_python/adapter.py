"""Playwright Python automation adapter."""

from __future__ import annotations

from typing import Any

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import LocatorSpec
from xpath_healer.utils.text import coerce_bool


class PlaywrightRuntimeLocator:
    def __init__(self, locator: Any) -> None:
        self.raw = locator

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)

    async def count(self) -> int:
        return int(await self.raw.count())

    def nth(self, index: int) -> "PlaywrightRuntimeLocator":
        return PlaywrightRuntimeLocator(self.raw.nth(index))

    async def is_visible(self) -> bool:
        return bool(await self.raw.is_visible())

    async def is_enabled(self) -> bool:
        return bool(await self.raw.is_enabled())

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        if arg is None:
            return await self.raw.evaluate(script)
        return await self.raw.evaluate(script, arg)

    async def bounding_box(self) -> dict[str, float] | None:
        box = await self.raw.bounding_box()
        if not box:
            return None
        return {
            "x": float(box["x"]),
            "y": float(box["y"]),
            "width": float(box["width"]),
            "height": float(box["height"]),
        }


class PlaywrightPythonAdapter(AutomationAdapter):
    name = "playwright_python"

    async def resolve_locator(self, root: Any, locator_spec: LocatorSpec) -> PlaywrightRuntimeLocator:
        base = root.raw if isinstance(root, PlaywrightRuntimeLocator) else root
        if locator_spec.scope:
            base = (await self.resolve_locator(root, locator_spec.scope)).raw

        if locator_spec.kind == "css":
            locator = base.locator(locator_spec.value)
        elif locator_spec.kind == "xpath":
            value = locator_spec.value if locator_spec.value.startswith("xpath=") else f"xpath={locator_spec.value}"
            locator = base.locator(value)
        elif locator_spec.kind == "pw":
            locator = base.locator(locator_spec.value)
        elif locator_spec.kind == "text":
            locator = base.get_by_text(
                locator_spec.value,
                exact=coerce_bool(locator_spec.options.get("exact"), default=False),
            )
        else:
            role = str(locator_spec.options.get("role") or locator_spec.value)
            kwargs: dict[str, Any] = {}
            for key in ("name", "exact", "checked", "disabled", "pressed", "selected"):
                if key in locator_spec.options:
                    kwargs[key] = locator_spec.options[key]
            locator = base.get_by_role(role, **kwargs)

        has_text = locator_spec.options.get("has_text")
        if has_text and hasattr(locator, "filter"):
            locator = locator.filter(has_text=str(has_text))

        nth_value = locator_spec.options.get("nth")
        if nth_value is not None and hasattr(locator, "nth"):
            locator = locator.nth(int(nth_value))

        if coerce_bool(locator_spec.options.get("first"), False) and hasattr(locator, "first"):
            locator = locator.first
        if coerce_bool(locator_spec.options.get("last"), False) and hasattr(locator, "last"):
            locator = locator.last

        return PlaywrightRuntimeLocator(locator)

    async def capture_page_html(self, page: Any) -> str:
        html = await page.evaluate("() => document.documentElement ? document.documentElement.outerHTML : ''")
        return html or ""
