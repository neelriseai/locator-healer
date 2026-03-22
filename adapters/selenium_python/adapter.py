"""Selenium Python automation adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import LocatorSpec
from xpath_healer.utils.text import coerce_bool, normalize_text

try:  # pragma: no cover
    from selenium.webdriver.common.by import By as SeleniumBy
    from selenium.common.exceptions import StaleElementReferenceException
except Exception:  # pragma: no cover
    class SeleniumBy:
        CSS_SELECTOR = "css selector"
        XPATH = "xpath"

    class StaleElementReferenceException(Exception):
        pass


class SeleniumRuntimeLocator:
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

    def nth(self, index: int) -> "SeleniumRuntimeLocator":
        def _nth_resolver() -> list[Any]:
            elements = self._elements()
            if index < 0:
                idx = len(elements) + index
            else:
                idx = index
            if 0 <= idx < len(elements):
                return [elements[idx]]
            return []

        return SeleniumRuntimeLocator(self.driver, _nth_resolver)

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
        def _run() -> Any:
            elements = self._elements()
            if not elements:
                return None
            wrapped = _wrap_arrow_function(script)
            if arg is None:
                return self.driver.execute_script(wrapped, elements[0])
            return self.driver.execute_script(wrapped, elements[0], arg)

        return await asyncio.to_thread(_run)

    async def bounding_box(self) -> dict[str, float] | None:
        def _run() -> Any:
            elements = self._elements()
            if not elements:
                return None
            return self.driver.execute_script(
                "const r = arguments[0].getBoundingClientRect();"
                "return {x: r.x, y: r.y, width: r.width, height: r.height};",
                elements[0],
            )

        rect = await asyncio.to_thread(_run)
        if not rect:
            return None
        return {
            "x": float(rect["x"]),
            "y": float(rect["y"]),
            "width": float(rect["width"]),
            "height": float(rect["height"]),
        }


class SeleniumPythonAdapter(AutomationAdapter):
    name = "selenium_python"

    async def resolve_locator(self, root: Any, locator_spec: LocatorSpec) -> SeleniumRuntimeLocator:
        scope_root = root
        if locator_spec.scope:
            scope_root = await self.resolve_locator(root, locator_spec.scope)
        driver = _driver_for(scope_root)

        def _resolver() -> list[Any]:
            roots = _search_roots(scope_root)
            matched: list[Any] = []
            if locator_spec.kind in {"css", "pw"}:
                for current in roots:
                    matched.extend(_find_elements(current, SeleniumBy.CSS_SELECTOR, locator_spec.value))
            elif locator_spec.kind == "xpath":
                for current in roots:
                    matched.extend(_find_elements(current, SeleniumBy.XPATH, locator_spec.value))
            elif locator_spec.kind == "text":
                xpath = _text_xpath(locator_spec.value, exact=coerce_bool(locator_spec.options.get("exact"), False))
                for current in roots:
                    matched.extend(_find_elements(current, SeleniumBy.XPATH, xpath))
            else:
                matched = _find_role_elements(roots, locator_spec)

            matched = _dedupe_elements(matched)
            has_text = locator_spec.options.get("has_text")
            if has_text:
                needle = normalize_text(str(has_text))
                matched = [el for el in matched if needle in normalize_text(_element_name(el))]

            if coerce_bool(locator_spec.options.get("first"), False):
                matched = matched[:1]
            if coerce_bool(locator_spec.options.get("last"), False):
                matched = matched[-1:]

            nth_value = locator_spec.options.get("nth")
            if nth_value is not None:
                idx = int(nth_value)
                if idx < 0:
                    idx = len(matched) + idx
                matched = [matched[idx]] if 0 <= idx < len(matched) else []
            return matched

        return SeleniumRuntimeLocator(driver, _resolver)

    async def capture_page_html(self, page: Any) -> str:
        html = await asyncio.to_thread(
            page.execute_script,
            "return document.documentElement ? document.documentElement.outerHTML : '';",
        )
        return str(html or "")


def _driver_for(root: Any) -> Any:
    if isinstance(root, SeleniumRuntimeLocator):
        return root.driver
    return root


def _search_roots(root: Any) -> list[Any]:
    if isinstance(root, SeleniumRuntimeLocator):
        return root._elements()
    return [root]


def _find_elements(root: Any, by: str, value: str) -> list[Any]:
    method = getattr(root, "find_elements", None)
    if not callable(method):
        return []
    return list(method(by, value) or [])


def _dedupe_elements(elements: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[int] = set()
    for element in elements:
        marker = id(element)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(element)
    return out


def _element_name(element: Any) -> str:
    text = getattr(element, "text", "") or ""
    get_attr = getattr(element, "get_attribute", None)
    if callable(get_attr):
        aria_label = get_attr("aria-label") or ""
        if aria_label:
            return str(aria_label)
    driver = getattr(element, "parent", None)
    execute_script = getattr(driver, "execute_script", None)
    if callable(execute_script):
        try:
            label_text = execute_script(
                """
                const el = arguments[0];
                if (!el) return '';
                const labels = el.labels ? Array.from(el.labels) : [];
                const own = (el.innerText || el.textContent || '').trim();
                const labelText = labels
                  .map(label => (label.innerText || label.textContent || '').trim())
                  .filter(Boolean)
                  .join(' ')
                  .trim();
                return labelText || own || '';
                """,
                element,
            )
            if label_text:
                return str(label_text)
        except Exception:
            pass
    return str(text)


def _text_xpath(value: str, exact: bool) -> str:
    literal = _xpath_literal(value)
    if exact:
        expr = (
            f"normalize-space(.) = {literal} and "
            f"not(.//*[normalize-space(.) = {literal}])"
        )
    else:
        lowered = _xpath_literal(value.casefold())
        expr = (
            "contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            f"{lowered}) and "
            "not(.//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            f"{lowered})])"
        )
    return f"descendant-or-self::*[{expr}]"


def _find_role_elements(roots: list[Any], locator_spec: LocatorSpec) -> list[Any]:
    role = normalize_text(str(locator_spec.options.get("role") or locator_spec.value))
    matched: list[Any] = []
    for current in roots:
        matched.extend(_find_elements(current, SeleniumBy.CSS_SELECTOR, f'[role="{role}"]'))
        for css in _semantic_role_css(role):
            matched.extend(_find_elements(current, SeleniumBy.CSS_SELECTOR, css))

    name = locator_spec.options.get("name")
    if not name:
        return _dedupe_elements(matched)

    exact = coerce_bool(locator_spec.options.get("exact"), False)
    expected = normalize_text(str(name))
    filtered: list[Any] = []
    for element in _dedupe_elements(matched):
        actual = normalize_text(_element_name(element))
        if exact and actual == expected:
            filtered.append(element)
        elif not exact and expected in actual:
            filtered.append(element)
    return filtered


def _semantic_role_css(role: str) -> list[str]:
    mapping = {
        "button": ["button", 'input[type="button"]', 'input[type="submit"]'],
        "link": ["a"],
        "textbox": ["input", "textarea"],
        "combobox": ["select", "input"],
        "checkbox": ['input[type="checkbox"]'],
        "radio": ['input[type="radio"]'],
    }
    return mapping.get(role, [])


def _wrap_arrow_function(script: str) -> str:
    stripped = (script or "").strip()
    if "=>" in stripped:
        return f"return ({stripped})(arguments[0], arguments[1]);"
    if stripped.startswith("return "):
        return stripped
    return f"return {stripped}"


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    chunks: list[str] = []
    for idx, part in enumerate(parts):
        if part:
            chunks.append(f"'{part}'")
        if idx < len(parts) - 1:
            chunks.append('"\'"')
    return f"concat({', '.join(chunks)})"
