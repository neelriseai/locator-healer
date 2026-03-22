"""Small Selenium-like fakes for unit tests."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from xpath_healer.utils.text import normalize_text


@dataclass
class FakeSeleniumElement:
    tag: str
    text: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    visible: bool = True
    enabled: bool = True
    bbox: dict[str, float] | None = None
    driver: "FakeSeleniumDriver | None" = None
    parent: "FakeSeleniumDriver | None" = None

    def find_elements(self, by: str, value: str) -> list["FakeSeleniumElement"]:
        if self.driver is None:
            return []
        return self.driver.find_elements(by, value)

    def get_attribute(self, name: str) -> str | None:
        return self.attrs.get(name)

    def is_displayed(self) -> bool:
        return self.visible

    def is_enabled(self) -> bool:
        return self.enabled

    def _html(self) -> str:
        attrs = " ".join(f'{k}="{v}"' for k, v in self.attrs.items())
        if attrs:
            attrs = " " + attrs
        return f"<{self.tag}{attrs}>{self.text}</{self.tag}>"


class FakeSeleniumDriver:
    def __init__(self) -> None:
        self.elements: list[FakeSeleniumElement] = []
        self.selector_map: dict[tuple[str, str], list[FakeSeleniumElement]] = {}

    def add_element(
        self,
        element: FakeSeleniumElement,
        selectors: dict[str, list[str]] | None = None,
    ) -> None:
        element.driver = self
        element.parent = self
        self.elements.append(element)
        for by, values in (selectors or {}).items():
            for value in values:
                self.selector_map.setdefault((by, value), []).append(element)

    def find_elements(self, by: str, value: str) -> list[FakeSeleniumElement]:
        if (by, value) in self.selector_map:
            return list(self.selector_map[(by, value)])
        by_norm = normalize_text(by)
        if "css" in by_norm:
            return self._match_css(value)
        if "xpath" in by_norm:
            return self._match_xpath(value)
        return []

    def execute_script(self, script: str, *args: Any) -> Any:
        if "document.documentElement" in script:
            return self._html()

        element = args[0] if args else None
        extra_arg = args[1] if len(args) > 1 else None
        if element is None:
            return None

        if "getBoundingClientRect" in script:
            return element.bbox or {"x": 0.0, "y": 0.0, "width": 100.0, "height": 20.0}
        if "outerHTML" in script:
            return element._html()
        if "el.labels" in script and "labelText" in script:
            return element.attrs.get("data-label") or element.text
        if "compareDocumentPosition" in script:
            return {"following": True, "preceding": False}
        if "xpathFor(node)" in script and "cssFor(node)" in script:
            return {
                "xpath": element.attrs.get("_xpath", f"//*[@name='{element.attrs.get('name', element.tag)}']"),
                "css": element.attrs.get("_css", element.tag),
            }
        if "attributes" in script or "attrs" in script:
            return {
                "tag": element.tag.lower(),
                "type": normalize_text(element.attrs.get("type", "")),
                "role": normalize_text(element.attrs.get("role", "")),
                "text": element.text,
                "attrs": dict(element.attrs),
                "container": [],
                "following": True if extra_arg else True,
                "preceding": False,
            }
        return None

    def _html(self) -> str:
        body = "".join(element._html() for element in self.elements)
        return f"<html><body>{body}</body></html>"

    def _match_css(self, selector: str) -> list[FakeSeleniumElement]:
        selector = selector.strip()
        if not selector:
            return []
        if selector == "*":
            return list(self.elements)
        if selector.startswith("[role="):
            expected = selector[len('[role="'):-2]
            return [el for el in self.elements if normalize_text(el.attrs.get("role")) == normalize_text(expected)]

        attr_pat = re.compile(r"^(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*)?\[(?P<attr>[^=\]]+)=\"(?P<val>[^\"]+)\"\]$")
        m = attr_pat.match(selector)
        if m:
            tag = m.group("tag")
            attr = m.group("attr")
            val = m.group("val")
            return [
                el
                for el in self.elements
                if (not tag or el.tag.lower() == tag.lower()) and el.attrs.get(attr) == val
            ]

        type_pat = re.compile(r"^(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*)\[type=\"(?P<val>[^\"]+)\"\]$")
        tm = type_pat.match(selector)
        if tm:
            tag = tm.group("tag")
            val = tm.group("val")
            return [
                el
                for el in self.elements
                if el.tag.lower() == tag.lower() and normalize_text(el.attrs.get("type")) == normalize_text(val)
            ]

        return [el for el in self.elements if el.tag.lower() == selector.lower()]

    def _match_xpath(self, selector: str) -> list[FakeSeleniumElement]:
        selector = selector.strip()
        if not selector:
            return []
        attr_pat = re.compile(r"^//?\*?\[@(?P<attr>[-a-zA-Z0-9_]+)=(?P<quote>['\"])(?P<val>.+?)(?P=quote)\]$")
        m = attr_pat.match(selector)
        if m:
            attr = m.group("attr")
            val = m.group("val")
            return [el for el in self.elements if el.attrs.get(attr) == val]

        exact_pat = re.compile(r"normalize-space\(\.\)\s*=\s*(['\"])(?P<val>.+?)\1")
        exact = exact_pat.search(selector)
        if exact:
            expected = normalize_text(exact.group("val"))
            return [el for el in self.elements if normalize_text(el.text) == expected]

        contains_pat = re.compile(r"contains\(translate\(normalize-space\(\.\).*?,\s*(['\"])(?P<val>.+?)\1\)")
        contains = contains_pat.search(selector)
        if contains:
            expected = normalize_text(contains.group("val"))
            return [el for el in self.elements if expected in normalize_text(el.text)]

        return []
