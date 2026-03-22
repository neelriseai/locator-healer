"""Small fake Playwright-like objects for unit tests."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from xpath_healer.utils.text import normalize_text


@dataclass
class FakeElement:
    tag: str
    text: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    visible: bool = True
    enabled: bool = True
    bbox: dict[str, float] | None = None

    async def is_visible(self) -> bool:
        return self.visible

    async def is_enabled(self) -> bool:
        return self.enabled

    async def inner_text(self) -> str:
        return self.text

    async def bounding_box(self) -> dict[str, float] | None:
        return self.bbox or {"x": 0.0, "y": 0.0, "width": 100.0, "height": 20.0}

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        if "outerHTML" in script:
            return self._html()
        if "compareDocumentPosition" in script:
            return {"following": True, "preceding": False}
        if "attributes" in script or "attrs" in script:
            return {
                "tag": self.tag.lower(),
                "type": normalize_text(self.attrs.get("type", "")),
                "role": normalize_text(self.attrs.get("role", "")),
                "text": self.text,
                "controlTag": normalize_text(self.attrs.get("data-control-tag", "")),
                "controlType": normalize_text(self.attrs.get("data-control-type", "")),
                "controlRole": normalize_text(self.attrs.get("data-control-role", "")),
                "proxyLabelTag": normalize_text(self.attrs.get("data-proxy-label-tag", "")),
                "proxyLabelText": self.attrs.get("data-proxy-label-text", ""),
                "proxyControlTag": normalize_text(self.attrs.get("data-proxy-control-tag", "")),
                "proxyControlType": normalize_text(self.attrs.get("data-proxy-control-type", "")),
                "proxyControlRole": normalize_text(self.attrs.get("data-proxy-control-role", "")),
                "attrs": dict(self.attrs),
                "container": [],
            }
        return None

    def _html(self) -> str:
        attrs = " ".join(f'{k}="{v}"' for k, v in self.attrs.items())
        if attrs:
            attrs = " " + attrs
        return f"<{self.tag}{attrs}>{self.text}</{self.tag}>"


class FakeLocator:
    def __init__(self, page: "FakePage", elements: list[FakeElement]) -> None:
        self.page = page
        self.elements = elements

    async def count(self) -> int:
        return len(self.elements)

    def nth(self, idx: int) -> "FakeLocator":
        if idx < 0:
            idx = len(self.elements) + idx
        if 0 <= idx < len(self.elements):
            return FakeLocator(self.page, [self.elements[idx]])
        return FakeLocator(self.page, [])

    @property
    def first(self) -> "FakeLocator":
        return self.nth(0)

    @property
    def last(self) -> "FakeLocator":
        return self.nth(-1)

    def filter(self, has_text: str | None = None) -> "FakeLocator":
        if has_text is None:
            return self
        needle = normalize_text(has_text)
        return FakeLocator(
            self.page,
            [el for el in self.elements if needle in normalize_text(el.text)],
        )

    def locator(self, selector: str) -> "FakeLocator":
        return self.page.locator(selector)

    def get_by_text(self, text: str, exact: bool = False) -> "FakeLocator":
        return self.page.get_by_text(text, exact=exact)

    def get_by_role(self, role: str, **kwargs: Any) -> "FakeLocator":
        return self.page.get_by_role(role, **kwargs)

    async def is_visible(self) -> bool:
        return bool(self.elements and self.elements[0].visible)

    async def is_enabled(self) -> bool:
        return bool(self.elements and self.elements[0].enabled)

    async def inner_text(self) -> str:
        return self.elements[0].text if self.elements else ""

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        if not self.elements:
            return None
        return await self.elements[0].evaluate(script, arg)

    async def bounding_box(self) -> dict[str, float] | None:
        if not self.elements:
            return None
        return await self.elements[0].bounding_box()


class FakePage:
    def __init__(self) -> None:
        self.elements: list[FakeElement] = []
        self.selector_map: dict[str, list[FakeElement]] = {}

    def add_element(self, element: FakeElement, selectors: list[str] | None = None) -> None:
        self.elements.append(element)
        for selector in selectors or []:
            self.selector_map.setdefault(selector, []).append(element)

    def register_selector(self, selector: str, elements: list[FakeElement]) -> None:
        self.selector_map[selector] = elements

    def locator(self, selector: str) -> FakeLocator:
        if selector in self.selector_map:
            return FakeLocator(self, list(self.selector_map[selector]))

        if selector.startswith("xpath="):
            raw = selector[6:]
            if raw in self.selector_map:
                return FakeLocator(self, list(self.selector_map[raw]))
            return FakeLocator(self, [])

        return FakeLocator(self, self._match_css(selector))

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        expected = normalize_text(text)
        if exact:
            matched = [el for el in self.elements if normalize_text(el.text) == expected]
        else:
            matched = [el for el in self.elements if expected in normalize_text(el.text)]
        return FakeLocator(self, matched)

    def get_by_role(self, role: str, **kwargs: Any) -> FakeLocator:
        expected_role = normalize_text(role)
        expected_name = kwargs.get("name")
        exact = bool(kwargs.get("exact"))
        matched: list[FakeElement] = []
        for element in self.elements:
            role_value = normalize_text(element.attrs.get("role", ""))
            if role_value != expected_role and not self._tag_matches_role(element, expected_role):
                continue
            if expected_name:
                left = normalize_text(expected_name)
                right = normalize_text(element.text)
                if exact and left != right:
                    continue
                if not exact and left not in right:
                    continue
            matched.append(element)
        return FakeLocator(self, matched)

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        if "document.documentElement" in script:
            return self._html()
        return None

    def _html(self) -> str:
        body = "".join(el._html() for el in self.elements)
        return f"<html><body>{body}</body></html>"

    @staticmethod
    def _tag_matches_role(element: FakeElement, expected_role: str) -> bool:
        tag = element.tag.lower()
        if expected_role == "button":
            return tag == "button" or (tag == "input" and normalize_text(element.attrs.get("type")) in {"submit", "button"})
        if expected_role == "link":
            return tag == "a"
        if expected_role == "textbox":
            return tag in {"input", "textarea"}
        return False

    def _match_css(self, selector: str) -> list[FakeElement]:
        selector = selector.strip()
        if not selector:
            return []
        if selector == "*":
            return list(self.elements)

        matched: list[FakeElement] = []
        parts = [part.strip() for part in selector.split(",") if part.strip()]
        for part in parts:
            matched.extend(self._match_css_part(part))

        uniq: list[FakeElement] = []
        seen: set[int] = set()
        for element in matched:
            key = id(element)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(element)
        return uniq

    def _match_css_part(self, part: str) -> list[FakeElement]:
        attr_pat = re.compile(r"^(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*)?\[(?P<attr>[^=\]]+)=\"(?P<val>[^\"]+)\"\]$")
        m = attr_pat.match(part)
        if m:
            tag = m.group("tag")
            attr = m.group("attr")
            val = m.group("val")
            out = []
            for element in self.elements:
                if tag and element.tag.lower() != tag.lower():
                    continue
                if element.attrs.get(attr) == val:
                    out.append(element)
            return out

        return [el for el in self.elements if el.tag.lower() == part.lower()]
