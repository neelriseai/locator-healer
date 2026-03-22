"""Page indexing layer for deterministic candidate ranking."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from xpath_healer.core.fingerprint import FingerprintService
from xpath_healer.core.models import BuildInput, ElementMeta, ElementSignature, IndexedElement, LocatorSpec, PageIndex
from xpath_healer.utils.text import fuzzy_ratio, normalize_text


ROLE_BY_FIELD_TYPE: dict[str, str] = {
    "button": "button",
    "link": "link",
    "textbox": "textbox",
    "input": "textbox",
    "dropdown": "combobox",
    "combobox": "combobox",
    "checkbox": "checkbox",
    "radio": "radio",
}


SCORING_WEIGHTS: dict[str, float] = {
    "text_similarity": 0.25,
    "container_similarity": 0.20,
    "id_similarity": 0.15,
    "fingerprint_similarity": 0.15,
    "role_match": 0.10,
    "neighbor_similarity": 0.10,
    "position_similarity": 0.05,
}


@dataclass(slots=True)
class RankedIndexedElement:
    element: IndexedElement
    locator: LocatorSpec
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class _ExpectedProfile:
    text: str = ""
    role: str = ""
    id_tokens: list[str] = field(default_factory=list)
    container_tokens: list[str] = field(default_factory=list)
    neighbor_text: str = ""
    position_signature: str = ""
    fingerprint: Any = None


@dataclass(slots=True)
class _FallbackNode:
    tag: str
    attrs: dict[str, str]
    parent_index: int | None
    children: list[int] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)


class _SimpleHtmlTreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[_FallbackNode] = []
        self._stack: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent_index = self._stack[-1] if self._stack else None
        attr_map: dict[str, str] = {}
        for key, value in attrs:
            key_text = str(key or "").strip()
            if not key_text:
                continue
            value_text = str(value or "").strip()
            if value_text:
                attr_map[key_text] = value_text
        node = _FallbackNode(
            tag=tag,
            attrs=attr_map,
            parent_index=parent_index,
        )
        self.nodes.append(node)
        idx = len(self.nodes) - 1
        if parent_index is not None and 0 <= parent_index < len(self.nodes):
            self.nodes[parent_index].children.append(idx)
        self._stack.append(idx)

    def handle_endtag(self, tag: str) -> None:
        tag_norm = normalize_text(tag)
        if not tag_norm:
            return
        for idx in range(len(self._stack) - 1, -1, -1):
            node_index = self._stack[idx]
            node_tag = normalize_text(self.nodes[node_index].tag)
            if node_tag == tag_norm:
                del self._stack[idx:]
                break

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        text = str(data or "").strip()
        if not text:
            return
        node_index = self._stack[-1]
        if 0 <= node_index < len(self.nodes):
            self.nodes[node_index].text_parts.append(text)


class PageIndexer:
    def __init__(self, max_elements: int = 400, top_k: int = 5, snapshot_version: str = "v1") -> None:
        self.max_elements = max(20, int(max_elements))
        self.top_k = max(1, int(top_k))
        self.snapshot_version = snapshot_version
        self._fingerprint = FingerprintService()

    @staticmethod
    def dom_hash(html: str) -> str:
        payload = (html or "").encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def build_page_index(self, app_id: str, page_name: str, html: str, dom_hash_value: str | None = None) -> PageIndex:
        page_index = PageIndex(
            app_id=app_id,
            page_name=page_name,
            dom_hash=dom_hash_value or self.dom_hash(html),
            snapshot_version=self.snapshot_version,
        )
        soup = self._parse(html)
        if soup is None:
            page_index.elements = self._build_elements_without_bs4(html)
            return page_index

        elements: list[IndexedElement] = []
        for ordinal, node in enumerate(soup.find_all(True)):
            if len(elements) >= self.max_elements:
                break
            tag = normalize_text(getattr(node, "name", ""))
            if not self._is_indexable(node, tag):
                continue

            attrs = self._normalized_attrs(getattr(node, "attrs", {}))
            text = " ".join(str(node.get_text(" ", strip=True) or "").split())
            normalized_text = normalize_text(text)
            attr_id = attrs.get("id") or attrs.get("data-testid") or ""
            attr_name = attrs.get("name") or attrs.get("formcontrolname") or ""
            class_tokens = [normalize_text(token) for token in attrs.get("class", "").split() if normalize_text(token)]
            role = normalize_text(attrs.get("role") or self._infer_role(tag, attrs))
            aria_label = str(attrs.get("aria-label") or "")
            placeholder = str(attrs.get("placeholder") or "")
            container_tokens = self._container_tokens(node)
            container_path = ">".join(container_tokens[:5])
            parent_signature = ">".join(container_tokens[:2])
            neighbor_text = self._neighbor_text(node)
            position_signature = self._position_signature(node)
            css = self._css_selector(tag, attrs, class_tokens)
            xpath = self._xpath_selector(tag, attrs, text)
            element_name = self._element_name(tag, attrs, ordinal)

            signature = ElementSignature(
                tag=tag,
                stable_attrs=self._stable_attrs(attrs),
                short_text=text[:140],
                container_path=container_tokens[:4],
                component_kind=role or None,
            )
            fingerprint = self._fingerprint.build(
                signature,
                field_type=self._field_type_for_role(role, tag),
                element_name=element_name,
            )

            elements.append(
                IndexedElement(
                    element_id=str(uuid.uuid4()),
                    element_name=element_name,
                    tag=tag,
                    text=text,
                    normalized_text=normalized_text,
                    attr_id=attr_id,
                    attr_name=attr_name,
                    class_tokens=class_tokens,
                    role=role,
                    aria_label=aria_label,
                    placeholder=placeholder,
                    container_path=container_path,
                    parent_signature=parent_signature,
                    neighbor_text=neighbor_text,
                    position_signature=position_signature,
                    xpath=xpath,
                    css=css,
                    fingerprint_hash=fingerprint.hash_value,
                    metadata_json={"attrs": attrs, "ordinal": ordinal},
                )
            )

        page_index.elements = elements
        return page_index

    def rank_candidates(
        self,
        page_index: PageIndex,
        inp: BuildInput,
        meta: ElementMeta | None,
    ) -> list[RankedIndexedElement]:
        if not page_index.elements:
            return []

        expected = self._expected_profile(inp, meta)
        ranked: list[RankedIndexedElement] = []
        for element in page_index.elements:
            locator = self._locator_for(element)
            if locator is None:
                continue
            score, breakdown = self._score_element(expected, element, inp.field_type)
            if score <= 0.0:
                continue
            ranked.append(
                RankedIndexedElement(
                    element=element,
                    locator=locator,
                    score=round(score, 6),
                    breakdown={key: round(value, 6) for key, value in breakdown.items()},
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[: self.top_k]

    @staticmethod
    def _parse(html: str) -> Any | None:
        if not html:
            return None
        try:
            from bs4 import BeautifulSoup  # type: ignore

            return BeautifulSoup(html, "lxml")
        except Exception:
            try:
                from bs4 import BeautifulSoup  # type: ignore

                return BeautifulSoup(html, "html.parser")
            except Exception:
                return None

    def _build_elements_without_bs4(self, html: str) -> list[IndexedElement]:
        parser = _SimpleHtmlTreeParser()
        try:
            parser.feed(html or "")
            parser.close()
        except Exception:
            return []

        elements: list[IndexedElement] = []
        for ordinal, node in enumerate(parser.nodes):
            if len(elements) >= self.max_elements:
                break
            tag = normalize_text(node.tag)
            if not tag:
                continue
            if not self._is_indexable_fallback(node, tag):
                continue

            attrs = self._normalized_attrs(node.attrs)
            text = " ".join(part.strip() for part in node.text_parts if part.strip())
            normalized_text = normalize_text(text)
            attr_id = attrs.get("id") or attrs.get("data-testid") or ""
            attr_name = attrs.get("name") or attrs.get("formcontrolname") or ""
            class_tokens = [normalize_text(token) for token in attrs.get("class", "").split() if normalize_text(token)]
            role = normalize_text(attrs.get("role") or self._infer_role(tag, attrs))
            aria_label = str(attrs.get("aria-label") or "")
            placeholder = str(attrs.get("placeholder") or "")
            container_tokens = self._container_tokens_fallback(parser.nodes, node.parent_index)
            container_path = ">".join(container_tokens[:5])
            parent_signature = ">".join(container_tokens[:2])
            neighbor_text = self._neighbor_text_fallback(parser.nodes, node.parent_index, ordinal)
            position_signature = self._position_signature_fallback(parser.nodes, node.parent_index, ordinal, tag)
            css = self._css_selector(tag, attrs, class_tokens)
            xpath = self._xpath_selector(tag, attrs, text)
            element_name = self._element_name(tag, attrs, ordinal)

            signature = ElementSignature(
                tag=tag,
                stable_attrs=self._stable_attrs(attrs),
                short_text=text[:140],
                container_path=container_tokens[:4],
                component_kind=role or None,
            )
            fingerprint = self._fingerprint.build(
                signature,
                field_type=self._field_type_for_role(role, tag),
                element_name=element_name,
            )

            elements.append(
                IndexedElement(
                    element_id=str(uuid.uuid4()),
                    element_name=element_name,
                    tag=tag,
                    text=text,
                    normalized_text=normalized_text,
                    attr_id=attr_id,
                    attr_name=attr_name,
                    class_tokens=class_tokens,
                    role=role,
                    aria_label=aria_label,
                    placeholder=placeholder,
                    container_path=container_path,
                    parent_signature=parent_signature,
                    neighbor_text=neighbor_text,
                    position_signature=position_signature,
                    xpath=xpath,
                    css=css,
                    fingerprint_hash=fingerprint.hash_value,
                    metadata_json={"attrs": attrs, "ordinal": ordinal},
                )
            )
        return elements

    @staticmethod
    def _is_indexable(node: Any, tag: str) -> bool:
        if not tag:
            return False
        attrs = getattr(node, "attrs", {}) or {}
        if attrs.get("id") or attrs.get("data-testid") or attrs.get("name") or attrs.get("role"):
            return True
        if tag in {"input", "textarea", "select", "button", "a", "label", "option", "td", "th"}:
            return True
        if tag in {"div", "span"}:
            text = normalize_text(str(node.get_text(" ", strip=True) or ""))
            return bool(text)
        return False

    @staticmethod
    def _is_indexable_fallback(node: _FallbackNode, tag: str) -> bool:
        attrs = node.attrs
        if attrs.get("id") or attrs.get("data-testid") or attrs.get("name") or attrs.get("role"):
            return True
        if tag in {"input", "textarea", "select", "button", "a", "label", "option", "td", "th"}:
            return True
        if tag in {"div", "span"}:
            text = normalize_text(" ".join(node.text_parts))
            return bool(text)
        return False

    @staticmethod
    def _normalized_attrs(raw_attrs: dict[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, value in dict(raw_attrs or {}).items():
            key_norm = str(key).strip()
            if not key_norm:
                continue
            if isinstance(value, (list, tuple)):
                text = " ".join(str(item).strip() for item in value if str(item).strip())
            else:
                text = str(value).strip()
            if not text:
                continue
            out[key_norm] = text
        return out

    @staticmethod
    def _stable_attrs(attrs: dict[str, str]) -> dict[str, str]:
        keys = ("id", "data-testid", "name", "formcontrolname", "role", "placeholder", "type", "aria-label", "col-id")
        return {key: value for key in keys if (value := attrs.get(key))}

    @staticmethod
    def _container_tokens(node: Any) -> list[str]:
        out: list[str] = []
        current = getattr(node, "parent", None)
        while current is not None:
            name = normalize_text(getattr(current, "name", ""))
            if not name or name == "[document]":
                break
            attrs = PageIndexer._normalized_attrs(getattr(current, "attrs", {}))
            if attrs.get("id"):
                token = f"{name}#{normalize_text(attrs['id'])}"
            elif attrs.get("data-testid"):
                token = f"{name}[testid={normalize_text(attrs['data-testid'])}]"
            elif attrs.get("role"):
                token = f"{name}[role={normalize_text(attrs['role'])}]"
            elif attrs.get("class"):
                cls = normalize_text(attrs["class"].split()[0])
                token = f"{name}.{cls}" if cls else name
            else:
                token = name
            out.append(token)
            if len(out) >= 6:
                break
            current = getattr(current, "parent", None)
        return out

    @staticmethod
    def _container_tokens_fallback(nodes: list[_FallbackNode], parent_index: int | None) -> list[str]:
        out: list[str] = []
        current_index = parent_index
        while current_index is not None and 0 <= current_index < len(nodes):
            node = nodes[current_index]
            name = normalize_text(node.tag)
            if not name:
                break
            attrs = PageIndexer._normalized_attrs(node.attrs)
            if attrs.get("id"):
                token = f"{name}#{normalize_text(attrs['id'])}"
            elif attrs.get("data-testid"):
                token = f"{name}[testid={normalize_text(attrs['data-testid'])}]"
            elif attrs.get("role"):
                token = f"{name}[role={normalize_text(attrs['role'])}]"
            elif attrs.get("class"):
                cls = normalize_text(attrs["class"].split()[0])
                token = f"{name}.{cls}" if cls else name
            else:
                token = name
            out.append(token)
            if len(out) >= 6:
                break
            current_index = node.parent_index
        return out

    @staticmethod
    def _neighbor_text(node: Any) -> str:
        values: list[str] = []
        previous = getattr(node, "find_previous_sibling", lambda: None)()
        nxt = getattr(node, "find_next_sibling", lambda: None)()
        for sibling in (previous, nxt):
            if sibling is None:
                continue
            text = normalize_text(str(sibling.get_text(" ", strip=True) or ""))
            if text:
                values.append(text)
        return " ".join(values[:2])

    @staticmethod
    def _neighbor_text_fallback(nodes: list[_FallbackNode], parent_index: int | None, node_index: int) -> str:
        siblings = [idx for idx, node in enumerate(nodes) if node.parent_index == parent_index]
        if not siblings:
            return ""
        pos = siblings.index(node_index) if node_index in siblings else -1
        if pos < 0:
            return ""
        out: list[str] = []
        for sibling_pos in (pos - 1, pos + 1):
            if sibling_pos < 0 or sibling_pos >= len(siblings):
                continue
            sibling = nodes[siblings[sibling_pos]]
            text = normalize_text(" ".join(sibling.text_parts))
            if text:
                out.append(text)
        return " ".join(out[:2])

    @staticmethod
    def _position_signature(node: Any) -> str:
        tag = normalize_text(getattr(node, "name", ""))
        if not tag:
            return ""
        index = 1
        prev = getattr(node, "previous_sibling", None)
        while prev is not None:
            if normalize_text(getattr(prev, "name", "")) == tag:
                index += 1
            prev = getattr(prev, "previous_sibling", None)
        return f"{tag}:{index}"

    @staticmethod
    def _position_signature_fallback(
        nodes: list[_FallbackNode],
        parent_index: int | None,
        node_index: int,
        tag: str,
    ) -> str:
        siblings = [idx for idx, node in enumerate(nodes) if node.parent_index == parent_index]
        count = 0
        for idx in siblings:
            if normalize_text(nodes[idx].tag) == tag:
                count += 1
            if idx == node_index:
                break
        if count <= 0:
            count = 1
        return f"{tag}:{count}"

    @staticmethod
    def _element_name(tag: str, attrs: dict[str, str], ordinal: int) -> str:
        seed = attrs.get("data-testid") or attrs.get("id") or attrs.get("name") or attrs.get("aria-label") or tag
        seed = normalize_text(seed).replace(" ", "_")
        if not seed:
            seed = "element"
        return f"{seed}_{ordinal}"

    @staticmethod
    def _field_type_for_role(role: str, tag: str) -> str:
        role_norm = normalize_text(role)
        if role_norm:
            if role_norm in {"textbox", "combobox", "checkbox", "radio", "button", "link"}:
                return role_norm
            return "generic"
        if tag in {"input", "textarea"}:
            return "textbox"
        if tag == "select":
            return "dropdown"
        if tag == "button":
            return "button"
        if tag == "a":
            return "link"
        return "generic"

    @staticmethod
    def _infer_role(tag: str, attrs: dict[str, str]) -> str:
        if attrs.get("role"):
            return attrs["role"]
        if tag == "button":
            return "button"
        if tag == "a":
            return "link"
        if tag in {"input", "textarea"}:
            input_type = normalize_text(attrs.get("type"))
            if input_type in {"checkbox", "radio"}:
                return input_type
            return "textbox"
        if tag == "select":
            return "combobox"
        return ""

    @staticmethod
    def _css_selector(tag: str, attrs: dict[str, str], class_tokens: list[str]) -> str:
        if attrs.get("data-testid"):
            return f'[data-testid="{PageIndexer._css_escape(attrs["data-testid"])}"]'
        if attrs.get("id"):
            return f'[id="{PageIndexer._css_escape(attrs["id"])}"]'
        if attrs.get("name") and tag:
            return f'{tag}[name="{PageIndexer._css_escape(attrs["name"])}"]'
        if attrs.get("aria-label") and tag in {"input", "textarea", "button", "a"}:
            return f'{tag}[aria-label="{PageIndexer._css_escape(attrs["aria-label"])}"]'
        if attrs.get("placeholder") and tag in {"input", "textarea"}:
            return f'{tag}[placeholder="{PageIndexer._css_escape(attrs["placeholder"])}"]'
        if class_tokens:
            return f"{tag}.{class_tokens[0]}" if tag else f".{class_tokens[0]}"
        return tag

    @staticmethod
    def _xpath_selector(tag: str, attrs: dict[str, str], text: str) -> str:
        if attrs.get("id"):
            return f'//*[@id={PageIndexer._xpath_literal(attrs["id"])}]'
        if attrs.get("data-testid"):
            return f'//*[@data-testid={PageIndexer._xpath_literal(attrs["data-testid"])}]'
        if attrs.get("name") and tag:
            return f"//{tag}[@name={PageIndexer._xpath_literal(attrs['name'])}]"
        if text and tag in {"button", "a", "label"}:
            return f"//{tag}[normalize-space()={PageIndexer._xpath_literal(text)}]"
        return f"//{tag}" if tag else ""

    @staticmethod
    def _css_escape(value: str) -> str:
        return str(value).replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _xpath_literal(value: str) -> str:
        text = str(value)
        if "'" not in text:
            return f"'{text}'"
        if '"' not in text:
            return f'"{text}"'
        parts = text.split("'")
        quoted = ", \"'\", ".join(f"'{part}'" for part in parts)
        return f"concat({quoted})"

    def _expected_profile(self, inp: BuildInput, meta: ElementMeta | None) -> _ExpectedProfile:
        text_candidates = [
            inp.intent.text,
            inp.intent.label,
            inp.vars.get("text"),
            inp.vars.get("label"),
            inp.vars.get("label_text"),
            inp.vars.get("name"),
            inp.element_name.replace("_", " "),
        ]
        expected_text = ""
        for raw in text_candidates:
            token = normalize_text(raw or "")
            if token:
                expected_text = token
                break

        expected_role = normalize_text(inp.vars.get("role") or ROLE_BY_FIELD_TYPE.get(normalize_text(inp.field_type), ""))
        if not expected_role and meta and meta.signature:
            expected_role = normalize_text(meta.signature.stable_attrs.get("role"))

        id_tokens: list[str] = []
        for key in ("id", "data-testid", "name", "formcontrolname"):
            value = inp.vars.get(key)
            token = normalize_text(value or "")
            if token:
                id_tokens.append(token)
        if meta and meta.signature:
            for key in ("id", "data-testid", "name", "formcontrolname"):
                value = meta.signature.stable_attrs.get(key)
                token = normalize_text(value or "")
                if token:
                    id_tokens.append(token)

        container_tokens: list[str] = []
        for raw in (
            inp.vars.get("container"),
            inp.vars.get("parent"),
            inp.vars.get("section"),
            inp.page_name,
        ):
            token = normalize_text(raw or "")
            if token:
                container_tokens.extend(self._split_tokens(token))
        if meta and meta.signature:
            for item in meta.signature.container_path:
                container_tokens.extend(self._split_tokens(normalize_text(item)))

        neighbor_text = normalize_text(
            inp.vars.get("neighbor")
            or inp.vars.get("near")
            or inp.vars.get("anchor_text")
            or inp.vars.get("context")
            or ""
        )
        position_signature = self._expected_position_signature(inp.vars)

        signature = meta.signature if meta and meta.signature else self._synthetic_signature(inp, expected_text)
        fingerprint = self._fingerprint.build(
            signature,
            field_type=inp.field_type,
            intent=inp.intent,
            element_name=inp.element_name,
        )

        return _ExpectedProfile(
            text=expected_text,
            role=expected_role,
            id_tokens=self._dedupe_tokens(id_tokens),
            container_tokens=self._dedupe_tokens(container_tokens),
            neighbor_text=neighbor_text,
            position_signature=position_signature,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _synthetic_signature(inp: BuildInput, expected_text: str) -> ElementSignature:
        field_tag_map = {
            "textbox": "input",
            "input": "input",
            "button": "button",
            "link": "a",
            "dropdown": "select",
            "combobox": "select",
            "checkbox": "input",
            "radio": "input",
        }
        field_type = normalize_text(inp.field_type)
        tag = field_tag_map.get(field_type, "div")
        stable_attrs: dict[str, str] = {}
        for key in ("id", "data-testid", "name", "formcontrolname", "role", "placeholder", "type"):
            value = str(inp.vars.get(key) or "").strip()
            if value:
                stable_attrs[key] = value
        return ElementSignature(
            tag=tag,
            stable_attrs=stable_attrs,
            short_text=expected_text,
            container_path=[normalize_text(inp.page_name)] if inp.page_name else [],
            component_kind=None,
        )

    def _score_element(
        self,
        expected: _ExpectedProfile,
        element: IndexedElement,
        field_type: str,
    ) -> tuple[float, dict[str, float]]:
        component_scores: dict[str, float] = {}

        text_score = self._text_similarity(expected.text, element)
        if text_score is not None:
            component_scores["text_similarity"] = text_score

        container_score = self._container_similarity(expected.container_tokens, element.container_path)
        if container_score is not None:
            component_scores["container_similarity"] = container_score

        id_score = self._id_similarity(expected.id_tokens, element)
        if id_score is not None:
            component_scores["id_similarity"] = id_score

        fp_score = self._fingerprint_similarity(expected.fingerprint, element, field_type)
        if fp_score is not None:
            component_scores["fingerprint_similarity"] = fp_score

        role_score = self._role_match(expected.role, element, field_type)
        if role_score is not None:
            component_scores["role_match"] = role_score

        neighbor_score = self._neighbor_similarity(expected.neighbor_text, element.neighbor_text)
        if neighbor_score is not None:
            component_scores["neighbor_similarity"] = neighbor_score

        position_score = self._position_similarity(expected.position_signature, element.position_signature)
        if position_score is not None:
            component_scores["position_similarity"] = position_score

        if not component_scores:
            return 0.0, {}

        weighted_total = 0.0
        weighted_score = 0.0
        for key, score in component_scores.items():
            weight = SCORING_WEIGHTS.get(key, 0.0)
            if weight <= 0:
                continue
            weighted_total += weight
            weighted_score += weight * min(max(score, 0.0), 1.0)

        if weighted_total <= 0:
            return 0.0, {}
        return weighted_score / weighted_total, component_scores

    @staticmethod
    def _text_similarity(expected_text: str, element: IndexedElement) -> float | None:
        if not expected_text:
            return None
        candidates = [
            normalize_text(element.normalized_text),
            normalize_text(element.text),
            normalize_text(element.aria_label),
            normalize_text(element.attr_name),
        ]
        scores = [fuzzy_ratio(expected_text, item) for item in candidates if item]
        if not scores:
            return 0.0
        return max(scores)

    @staticmethod
    def _container_similarity(expected_tokens: list[str], container_path: str) -> float | None:
        if not expected_tokens:
            return None
        left = {token for token in expected_tokens if token}
        right = {token for token in PageIndexer._split_tokens(container_path) if token}
        if not right:
            return 0.0
        union = left | right
        if not union:
            return 0.0
        return len(left & right) / len(union)

    @staticmethod
    def _id_similarity(expected_tokens: list[str], element: IndexedElement) -> float | None:
        if not expected_tokens:
            return None
        candidate_tokens = [
            normalize_text(element.attr_id),
            normalize_text(element.attr_name),
        ]
        attrs = element.metadata_json.get("attrs") if isinstance(element.metadata_json, dict) else {}
        if isinstance(attrs, dict):
            for key in ("id", "data-testid", "name", "formcontrolname"):
                token = normalize_text(attrs.get(key) or "")
                if token:
                    candidate_tokens.append(token)
        candidate_tokens = [token for token in candidate_tokens if token]
        if not candidate_tokens:
            return 0.0
        return max(fuzzy_ratio(left, right) for left in expected_tokens for right in candidate_tokens)

    def _fingerprint_similarity(self, expected_fp: Any, element: IndexedElement, field_type: str) -> float | None:
        if expected_fp is None or not getattr(expected_fp, "text", ""):
            return None
        signature = self._signature_from_indexed_element(element)
        candidate_fp = self._fingerprint.build(
            signature,
            field_type=field_type,
            element_name=element.element_name,
        )
        return self._fingerprint.compare(expected_fp, candidate_fp).score

    @staticmethod
    def _signature_from_indexed_element(element: IndexedElement) -> ElementSignature:
        attrs = element.metadata_json.get("attrs") if isinstance(element.metadata_json, dict) else {}
        stable_attrs = {}
        if isinstance(attrs, dict):
            for key in ("id", "data-testid", "name", "formcontrolname", "role", "placeholder", "type", "aria-label", "col-id"):
                value = str(attrs.get(key) or "").strip()
                if value:
                    stable_attrs[key] = value
        if element.role and "role" not in stable_attrs:
            stable_attrs["role"] = element.role
        container_path = [token for token in element.container_path.split(">") if token][:4]
        return ElementSignature(
            tag=element.tag,
            stable_attrs=stable_attrs,
            short_text=element.text,
            container_path=container_path,
            component_kind=element.role or None,
        )

    @staticmethod
    def _role_match(expected_role: str, element: IndexedElement, field_type: str) -> float | None:
        if not expected_role:
            return None
        candidate_role = normalize_text(element.role)
        if not candidate_role:
            candidate_role = PageIndexer._infer_role_from_tag(element.tag)
        if not candidate_role:
            return 0.0
        if candidate_role == expected_role:
            return 1.0
        if expected_role in {"textbox", "combobox"} and candidate_role in {"textbox", "combobox"}:
            return 0.75
        if expected_role in {"button", "link"} and candidate_role in {"button", "link"}:
            return 0.70
        return 0.0

    @staticmethod
    def _infer_role_from_tag(tag: str) -> str:
        tag_norm = normalize_text(tag)
        if tag_norm == "button":
            return "button"
        if tag_norm == "a":
            return "link"
        if tag_norm in {"input", "textarea"}:
            return "textbox"
        if tag_norm == "select":
            return "combobox"
        return ""

    @staticmethod
    def _neighbor_similarity(expected_neighbor: str, candidate_neighbor: str) -> float | None:
        if not expected_neighbor:
            return None
        right = normalize_text(candidate_neighbor)
        if not right:
            return 0.0
        return fuzzy_ratio(expected_neighbor, right)

    @staticmethod
    def _position_similarity(expected_position: str, candidate_position: str) -> float | None:
        if not expected_position:
            return None
        left = normalize_text(expected_position)
        right = normalize_text(candidate_position)
        if not right:
            return 0.0
        if left == right:
            return 1.0
        return fuzzy_ratio(left, right)

    @staticmethod
    def _locator_for(element: IndexedElement) -> LocatorSpec | None:
        css_value = (element.css or "").strip()
        xpath_value = (element.xpath or "").strip()
        if css_value and css_value.casefold() not in {"*", "html", "body"}:
            return LocatorSpec(kind="css", value=css_value)
        if xpath_value:
            return LocatorSpec(kind="xpath", value=xpath_value)
        if element.role and element.text:
            return LocatorSpec(kind="role", value=element.role, options={"name": element.text, "exact": False})
        if element.text:
            return LocatorSpec(kind="text", value=element.text, options={"exact": False})
        if element.tag:
            return LocatorSpec(kind="css", value=element.tag)
        return None

    @staticmethod
    def _split_tokens(value: str) -> list[str]:
        raw = normalize_text(value)
        if not raw:
            return []
        return [token for token in re.split(r"[^a-z0-9:_-]+", raw) if token]

    @staticmethod
    def _dedupe_tokens(tokens: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            key = normalize_text(token)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out

    @staticmethod
    def _expected_position_signature(vars_map: dict[str, str]) -> str:
        for key in ("position", "occurrence", "index"):
            raw = vars_map.get(key)
            if raw is None:
                continue
            text = str(raw).strip()
            if not text:
                continue
            if text.isdigit():
                return f":{text}"
            return normalize_text(text)
        return ""
