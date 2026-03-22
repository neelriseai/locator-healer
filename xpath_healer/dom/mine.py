"""First-run robust candidate mining from DOM snapshot."""

from __future__ import annotations

from typing import Any

from xpath_healer.core.models import LocatorSpec
from xpath_healer.utils.text import normalize_text


class DomMiner:
    def __init__(self, max_candidates: int = 20) -> None:
        self.max_candidates = max_candidates

    def mine(
        self,
        html: str,
        field_type: str,
        vars_map: dict[str, str] | None,
        attribute_priority: list[str],
    ) -> list[LocatorSpec]:
        if not html:
            return []
        vars_map = vars_map or {}
        soup = self._parse(html)
        if soup is None:
            return []

        field_type_norm = normalize_text(field_type)
        label = vars_map.get("label") or vars_map.get("label_text")
        text_value = vars_map.get("text") or label
        col_id = vars_map.get("col-id") or vars_map.get("col_id")

        tags = self._tags_for(field_type_norm)
        candidates: list[LocatorSpec] = []
        seen: set[str] = set()
        for node in soup.find_all(tags):
            if len(candidates) >= self.max_candidates:
                break
            stable_attrs = {
                key: str(node.attrs.get(key))
                for key in attribute_priority
                if node.attrs.get(key) is not None and str(node.attrs.get(key)).strip()
            }
            if text_value:
                node_text = normalize_text(node.get_text(" ", strip=True))
                if node_text and normalize_text(text_value) not in node_text:
                    pass

            loc = self._build_from_attrs(stable_attrs, node.name, text_value, col_id)
            if not loc:
                continue
            loc_hash = loc.stable_hash()
            if loc_hash in seen:
                continue
            seen.add(loc_hash)
            candidates.append(loc)

        return candidates

    def _build_from_attrs(
        self,
        attrs: dict[str, str],
        tag: str,
        text_value: str | None,
        col_id: str | None,
    ) -> LocatorSpec | None:
        for key, value in attrs.items():
            if key == "role":
                return LocatorSpec(kind="role", value=value, options={"name": text_value} if text_value else {})
            selector = f'[{key}="{self._css_escape(value)}"]'
            return LocatorSpec(kind="css", value=selector)

        if col_id and tag in {"div", "span"}:
            return LocatorSpec(kind="css", value=f'[col-id="{self._css_escape(col_id)}"]')

        if text_value and tag in {"button", "a", "label"}:
            return LocatorSpec(kind="text", value=text_value, options={"exact": False})

        if tag:
            return LocatorSpec(kind="css", value=tag)
        return None

    @staticmethod
    def _css_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _parse(html: str) -> Any | None:
        try:
            from bs4 import BeautifulSoup  # type: ignore

            return BeautifulSoup(html, "lxml")
        except Exception:
            try:
                from bs4 import BeautifulSoup  # type: ignore

                return BeautifulSoup(html, "html.parser")
            except Exception:
                return None

    @staticmethod
    def _tags_for(field_type: str) -> list[str]:
        if field_type in {"textbox", "input"}:
            return ["input", "textarea"]
        if field_type in {"dropdown", "combobox"}:
            return ["select", "input", "div"]
        if field_type in {"button"}:
            return ["button", "a", "input"]
        if field_type in {"link"}:
            return ["a"]
        if field_type in {"checkbox", "radio"}:
            return ["input", "label", "div"]
        if field_type in {"gridcell", "grid_header", "gridheader"}:
            return ["div", "span", "td", "th"]
        return ["input", "textarea", "button", "a", "select", "div", "span"]

