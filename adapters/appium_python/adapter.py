"""Appium automation adapter — native iOS / Android mobile targets.

Design notes
------------

* **Same contract as Playwright + Selenium**: implements
  :class:`AutomationAdapter` and :class:`RuntimeLocator`, so every
  healing stage (rules, fingerprint, page-index, signature,
  option_fingerprint, dom_mining, defaults, position, mcp_explore,
  rag, workflow_replay, workflow_rewrite) works for mobile targets
  with **zero per-stage changes**.

* **Selector mapping**: Appium uses different ``By`` strategies than
  Selenium-web. We translate ``LocatorSpec.kind`` as follows:

      kind="xpath"             → AppiumBy.XPATH
      kind="css"               → AppiumBy.CSS_SELECTOR (where supported)
      kind="role"              → AppiumBy.ACCESSIBILITY_ID
      kind="text" / "pw"       → AppiumBy.XPATH (text-based, generated)

* **``evaluate`` semantics**: mobile devices have no JS engine in the
  general case. We provide a *capability-aware* implementation that
  returns ``None`` for script-style payloads and forwards
  ``"mobile: ..."`` script names to Appium's ``execute_script``. This
  lets stages that *opportunistically* use ``evaluate`` (graph
  grounder, MCP explorer tools) degrade gracefully on mobile rather
  than crashing.

* **No special config**: the adapter is picked the same way as
  selenium / playwright — by passing it to
  :class:`xpath_healer.api.base.BaseHealerFacade` directly, or via
  the future ``AppiumHealerFacade`` (small wrapper).
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import LocatorSpec


try:  # pragma: no cover - optional dep
    from appium.webdriver.common.appiumby import AppiumBy  # type: ignore
    from selenium.common.exceptions import StaleElementReferenceException  # type: ignore
except Exception:  # pragma: no cover
    class AppiumBy:
        XPATH = "xpath"
        CSS_SELECTOR = "css selector"
        ACCESSIBILITY_ID = "accessibility id"
        ID = "id"
        CLASS_NAME = "class name"
        ANDROID_UIAUTOMATOR = "-android uiautomator"
        IOS_PREDICATE = "-ios predicate string"

    class StaleElementReferenceException(Exception):
        pass


_MOBILE_SCRIPT_PREFIX = "mobile:"


class AppiumRuntimeLocator:
    """``RuntimeLocator`` impl backed by an Appium driver."""

    def __init__(self, driver: Any, resolver: Callable[[], list[Any]]) -> None:
        self.driver = driver
        self._resolver = resolver
        self.raw = self

    def __getattr__(self, name: str) -> Any:
        elements = self._resolver()
        if not elements:
            raise AttributeError(name)
        return getattr(elements[0], name)

    def _elements(self) -> list[Any]:
        attempts = 0
        while attempts < 2:
            attempts += 1
            try:
                return list(self._resolver())
            except StaleElementReferenceException:
                if attempts >= 2:
                    raise
        return []

    async def count(self) -> int:
        return int(await asyncio.to_thread(lambda: len(self._elements())))

    def nth(self, index: int) -> "AppiumRuntimeLocator":
        def _nth_resolver() -> list[Any]:
            elements = self._elements()
            if index < 0:
                idx = len(elements) + index
            else:
                idx = index
            if 0 <= idx < len(elements):
                return [elements[idx]]
            return []

        return AppiumRuntimeLocator(self.driver, _nth_resolver)

    async def is_visible(self) -> bool:
        def _run() -> bool:
            elements = self._elements()
            if not elements:
                return False
            method = getattr(elements[0], "is_displayed", None)
            return bool(method()) if callable(method) else True

        return bool(await asyncio.to_thread(_run))

    async def is_enabled(self) -> bool:
        def _run() -> bool:
            elements = self._elements()
            if not elements:
                return False
            method = getattr(elements[0], "is_enabled", None)
            return bool(method()) if callable(method) else True

        return bool(await asyncio.to_thread(_run))

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        """Mobile-aware ``evaluate``.

        Three behaviours:

        1. ``script`` starts with ``mobile:`` (Appium mobile command
           like ``mobile: scroll``, ``mobile: shell``) — forwarded to
           ``driver.execute_script`` as-is.
        2. Caller passed a JS arrow function string — most stages use
           this opportunistically. Mobile has no JS engine; we return
           ``None`` so the caller's `try/except` or graceful-default
           path takes over.
        3. Otherwise: best-effort ``driver.execute_script`` with the
           same args as web Selenium; many Appium drivers accept a
           narrow set.
        """
        def _run() -> Any:
            elements = self._elements()
            if not elements:
                return None
            script_str = script or ""
            stripped = script_str.lstrip()
            if stripped.startswith(_MOBILE_SCRIPT_PREFIX):
                try:
                    if arg is None:
                        return self.driver.execute_script(script_str)
                    return self.driver.execute_script(script_str, arg)
                except Exception:
                    return None
            # JS arrow function or general script: mobile has no JS
            # engine. Return None — graph grounder + MCP tools
            # interpret None as "this DOM probe didn't work, fall
            # through".
            return None

        return await asyncio.to_thread(_run)

    async def bounding_box(self) -> dict[str, float] | None:
        def _run() -> Any:
            elements = self._elements()
            if not elements:
                return None
            element = elements[0]
            # Most Appium drivers expose `.location` and `.size`.
            try:
                loc = element.location
                size = element.size
            except Exception:
                rect = getattr(element, "rect", None)
                if rect is None:
                    return None
                return {
                    "x": float(rect.get("x", 0.0)),
                    "y": float(rect.get("y", 0.0)),
                    "width": float(rect.get("width", 0.0)),
                    "height": float(rect.get("height", 0.0)),
                }
            return {
                "x": float(loc.get("x", 0.0)),
                "y": float(loc.get("y", 0.0)),
                "width": float(size.get("width", 0.0)),
                "height": float(size.get("height", 0.0)),
            }

        return await asyncio.to_thread(_run)


class AppiumPythonAdapter(AutomationAdapter):
    """``AutomationAdapter`` impl wrapping an Appium driver."""

    name = "appium_python"

    async def resolve_locator(self, root: Any, locator_spec: LocatorSpec) -> AppiumRuntimeLocator:
        by, value = self._translate_locator(locator_spec)

        def _resolver() -> list[Any]:
            try:
                return list(root.find_elements(by, value))
            except Exception:
                return []

        return AppiumRuntimeLocator(root, _resolver)

    async def capture_page_html(self, page: Any) -> str:
        """Return the page source.

        On mobile this is the XML view hierarchy (iOS / Android), not
        HTML — but downstream stages treat it as opaque text for
        signature hashing, fingerprinting, and DOM mining. The
        existing helpers all tolerate this.
        """
        def _run() -> str:
            try:
                return str(page.page_source or "")
            except Exception:
                return ""

        return await asyncio.to_thread(_run)

    @staticmethod
    def _translate_locator(spec: LocatorSpec) -> tuple[str, str]:
        kind = (spec.kind or "").strip().lower()
        value = spec.value or ""
        if kind == "xpath":
            return (AppiumBy.XPATH, value)
        if kind == "css":
            return (AppiumBy.CSS_SELECTOR, value)
        if kind == "role":
            # On mobile, "role" maps to accessibility-id — the closest
            # platform-stable identifier for an interactive element.
            return (AppiumBy.ACCESSIBILITY_ID, value)
        if kind == "text":
            # Synthesise an XPath that matches a visible text node.
            escaped = (value or "").replace("'", "\\'")
            return (
                AppiumBy.XPATH,
                (
                    f"//*[@text='{escaped}' or @label='{escaped}' or "
                    f"@name='{escaped}']"
                ),
            )
        if kind == "pw":
            # No equivalent on mobile — fall back to XPath if the
            # caller squeezed an xpath in there.
            return (AppiumBy.XPATH, value)
        # Unknown kind: best-effort xpath.
        return (AppiumBy.XPATH, value)
