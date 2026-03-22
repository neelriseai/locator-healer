"""Prompt payload builder utilities for RAG stage."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from xpath_healer.core.models import BuildInput
from xpath_healer.rag.prompt_dsl import build_prompt_dsl
from xpath_healer.utils.text import normalize_text


def build_prompt_payload(
    inp: BuildInput,
    dom_snippet: str,
    context_candidates: list[dict[str, Any]],
    dom_context: list[dict[str, Any]] | None = None,
    deep_graph: bool = False,
) -> dict[str, Any]:
    dom_signature = build_dom_signature(dom_snippet, deep_graph=deep_graph)
    compact_context = _compact_context_candidates(context_candidates)
    dom_context = dom_context if dom_context is not None else extract_dom_context(dom_snippet, deep_graph=deep_graph)
    return {
        "task": "suggest_locator_specs",
        "mode": "deep_graph" if deep_graph else "default",
        "field_type": inp.field_type,
        "dom_signature": dom_signature,
        "dsl_prompt": build_prompt_dsl(
            inp,
            dom_signature,
            compact_context,
            dom_context,
            deep_graph=deep_graph,
        ),
        "context": compact_context,
        "dom_context": dom_context,
        "rules": {
            "no_absolute_xpath_with_deep_indices": True,
            "avoid_positional_xpath": True,
            "prefer_css_or_role_when_unique": True,
            "bound_to_candidate_universe": True,
            "canonical_role_format": {
                "kind": "role",
                "value": "<aria-role-only>",
                "options": {"name": "<accessible-name>", "exact": False},
            },
            "canonical_text_format": {
                "kind": "text",
                "value": "<visible-text-only>",
                "options": {"exact": False},
            },
            "prefer_visible_proxy_for_toggles": True,
            "max_candidates": 5,
            "output_schema": {
                "kind": "css|xpath|role|text|pw",
                "value": "string",
                "options": "object",
                "confidence": "number [0..1], optional",
                "reason": "string, optional",
                "needs_more_context": "boolean, optional",
            },
        },
    }


def build_dom_signature(dom_snippet: str, deep_graph: bool = False) -> str:
    document = _bounded_document(dom_snippet, deep_graph=deep_graph)
    if not document:
        return ""
    tags = ("input", "button", "a", "select", "textarea", "label")
    counts = []
    for tag in tags:
        count = len(re.findall(fr"<\s*{tag}\b", document, flags=re.IGNORECASE))
        if count > 0:
            counts.append(f"{tag}:{count}")

    role_hits = re.findall(r'role\s*=\s*["\']([^"\']+)["\']', document, flags=re.IGNORECASE)
    testid_hits = re.findall(r'data-testid\s*=\s*["\']([^"\']+)["\']', document, flags=re.IGNORECASE)
    placeholder_hits = re.findall(r'placeholder\s*=\s*["\']([^"\']+)["\']', document, flags=re.IGNORECASE)
    labels = re.findall(r"<label[^>]*>(.*?)</label>", document, flags=re.IGNORECASE | re.DOTALL)

    token_limit = 8 if deep_graph else 4
    roles = _top_tokens(role_hits, limit=token_limit)
    testids = _top_tokens(testid_hits, limit=token_limit)
    placeholders = _top_tokens(placeholder_hits, limit=token_limit)
    label_tokens = _top_tokens([" ".join(item.split())[:40] for item in labels], limit=5 if deep_graph else 3)

    parts = [f"tags[{', '.join(counts)}]"] if counts else []
    if roles:
        parts.append(f"roles[{', '.join(roles)}]")
    if testids:
        parts.append(f"testids[{', '.join(testids)}]")
    if placeholders:
        parts.append(f"placeholders[{', '.join(placeholders)}]")
    if label_tokens:
        parts.append(f"labels[{', '.join(label_tokens)}]")

    compact_limit = 380 if deep_graph else 180
    compact = " ".join(_focused_dom_excerpt(document, deep_graph=deep_graph).split())
    compact = compact[:compact_limit] + ("..." if len(compact) > compact_limit else "")
    if compact:
        parts.append(f"sample={compact}")
    return " ".join(parts)


def extract_dom_context(dom_snippet: str, deep_graph: bool = False) -> list[dict[str, Any]]:
    parser = _DomContextParser(max_entities=120 if deep_graph else 60)
    try:
        parser.feed(_bounded_document(dom_snippet, deep_graph=deep_graph))
        parser.close()
    except Exception:
        return []
    return parser.entities()


def _top_tokens(values: list[str], limit: int = 4) -> list[str]:
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in values:
        token = " ".join((raw or "").split()).strip()
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(token[:40])
        if len(uniq) >= limit:
            break
    return uniq


def _compact_context_candidates(context_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    picked = context_candidates[:5]
    common_scope = _common_scope(picked)

    out: list[dict[str, Any]] = []
    for item in picked:
        if not isinstance(item, dict):
            continue
        compact: dict[str, Any] = {}
        for key in ("app_id", "page_name", "field_type"):
            value = item.get(key)
            if value is None:
                continue
            if common_scope.get(key) == value:
                continue
            compact[key] = value

        for key in ("element_name", "rerank_score"):
            value = item.get(key)
            if value is not None:
                compact[key] = value

        locator_payload = None
        for locator_key in ("locator", "last_good_locator", "robust_locator"):
            loc = item.get(locator_key)
            if isinstance(loc, dict) and loc.get("kind") and loc.get("value"):
                locator_payload = {"kind": loc.get("kind"), "value": loc.get("value")}
                break
        if locator_payload:
            compact["locator"] = locator_payload

        quality = item.get("quality_metrics")
        if isinstance(quality, dict):
            compact["quality"] = {
                "stability": quality.get("stability_score"),
                "uniqueness": quality.get("uniqueness_score"),
            }
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            if metadata.get("prompt_compact_text"):
                compact["prompt_compact_text"] = str(metadata.get("prompt_compact_text"))[:240]
            if metadata.get("fingerprint_tokens"):
                compact["fingerprint_tokens"] = list(metadata.get("fingerprint_tokens") or [])[:6]
        out.append(compact)
    return out


def _common_scope(items: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ("app_id", "page_name", "field_type")
    out: dict[str, Any] = {}
    if not items:
        return out
    for key in keys:
        value = None
        same = True
        for item in items:
            if not isinstance(item, dict):
                same = False
                break
            current = item.get(key)
            if value is None:
                value = current
            elif current != value:
                same = False
                break
        if same and value not in (None, ""):
            out[key] = value
    return out


def _bounded_document(dom_snippet: str, deep_graph: bool) -> str:
    limit = 120000 if deep_graph else 60000
    return (dom_snippet or "")[:limit]


def _focused_dom_excerpt(document: str, deep_graph: bool) -> str:
    if not document:
        return ""
    max_windows = 16 if deep_graph else 10
    radius = 220 if deep_graph else 160
    windows: list[tuple[int, int]] = []
    for pattern in (
        r"<\s*label\b",
        r"<\s*input\b",
        r"<\s*textarea\b",
        r"<\s*select\b",
        r"<\s*button\b",
        r'role\s*=\s*["\']',
        r'placeholder\s*=\s*["\']',
        r'aria-label\s*=\s*["\']',
    ):
        for match in re.finditer(pattern, document, flags=re.IGNORECASE):
            start = max(0, match.start() - radius)
            end = min(len(document), match.end() + radius)
            windows.append((start, end))
            if len(windows) >= max_windows:
                break
        if len(windows) >= max_windows:
            break
    if not windows:
        return document[: 1200 if deep_graph else 600]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(windows):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    excerpt = " ... ".join(document[start:end] for start, end in merged[:max_windows])
    return excerpt[: 2800 if deep_graph else 1400]


class _DomContextParser(HTMLParser):
    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    _ATTR_KEYS = (
        "id",
        "name",
        "placeholder",
        "type",
        "role",
        "data-testid",
        "aria-label",
        "href",
        "for",
    )

    def __init__(self, max_entities: int) -> None:
        super().__init__(convert_charrefs=True)
        self.max_entities = max_entities
        self._nodes: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []
        self._open_labels: list[int] = []
        self._explicit_labels: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_norm = tag.lower()
        attr_map = {str(key).strip().lower(): str(value or "").strip() for key, value in attrs}
        entity_index: int | None = None
        if len(self._nodes) < self.max_entities and self._should_track(tag_norm, attr_map):
            node = {
                "tag": tag_norm,
                "attrs": {key: attr_map.get(key, "") for key in self._ATTR_KEYS if attr_map.get(key)},
                "_text_parts": [],
                "_parent_label": self._open_labels[-1] if self._open_labels and tag_norm != "label" else None,
                "_control_type": "",
                "_control_role": "",
            }
            self._nodes.append(node)
            entity_index = len(self._nodes) - 1
            if tag_norm == "label":
                self._open_labels.append(entity_index)
                label_for = attr_map.get("for") or ""
                if label_for:
                    node["attrs"]["for"] = label_for
        self._bind_label_control(tag_norm, attr_map)
        if tag_norm in self._VOID_TAGS:
            return
        self._stack.append({"tag": tag_norm, "entity_index": entity_index})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag_norm = tag.lower()
        while self._stack:
            frame = self._stack.pop()
            entity_index = frame.get("entity_index")
            if entity_index is not None:
                self._finalize_node(entity_index)
                if frame["tag"] == "label" and self._open_labels and self._open_labels[-1] == entity_index:
                    self._open_labels.pop()
            if frame["tag"] == tag_norm:
                break

    def handle_data(self, data: str) -> None:
        text = _prompt_text(data)
        if not text:
            return
        for frame in reversed(self._stack):
            entity_index = frame.get("entity_index")
            if entity_index is None:
                continue
            self._nodes[entity_index]["_text_parts"].append(text)
            break

    def entities(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for index, node in enumerate(self._nodes):
            attrs = dict(node.get("attrs") or {})
            label = self._resolve_label(index, attrs)
            text = _prompt_text(" ".join(node.get("_text_parts") or []))
            control_role = str(node.get("_control_role") or "")
            control_type = str(node.get("_control_type") or "")
            entity = {
                "tag": node.get("tag"),
                "role": attrs.get("role") or control_role or _implicit_role(str(node.get("tag") or ""), attrs),
                "label": label or "",
                "text": text[:80],
                "attrs": {
                    key: value
                    for key, value in attrs.items()
                    if key in {"id", "name", "placeholder", "type", "data-testid", "aria-label", "href"}
                },
            }
            if control_type:
                entity["control_type"] = control_type
            if not entity["label"] and not entity["text"] and not entity["attrs"]:
                continue
            out.append(entity)
        return out[: self.max_entities]

    def _finalize_node(self, index: int) -> None:
        node = self._nodes[index]
        if node.get("tag") != "label":
            return
        label_for = str((node.get("attrs") or {}).get("for") or "").strip()
        label_text = _prompt_text(" ".join(node.get("_text_parts") or []))
        if label_for and label_text:
            self._explicit_labels[label_for] = label_text

    @staticmethod
    def _should_track(tag: str, attrs: dict[str, str]) -> bool:
        tag_norm = tag.lower()
        if tag_norm in {"input", "textarea", "select", "button", "a", "label"}:
            return True
        return bool(attrs.get("role"))

    def _resolve_label(self, index: int, attrs: dict[str, str]) -> str:
        if attrs.get("aria-label"):
            return _prompt_text(attrs["aria-label"])
        element_id = attrs.get("id") or ""
        if element_id and self._explicit_labels.get(element_id):
            return self._explicit_labels[element_id]
        parent_label_index = self._nodes[index].get("_parent_label")
        if isinstance(parent_label_index, int) and 0 <= parent_label_index < len(self._nodes):
            return _prompt_text(" ".join(self._nodes[parent_label_index].get("_text_parts") or []))
        if self._nodes[index].get("tag") == "button":
            return _prompt_text(" ".join(self._nodes[index].get("_text_parts") or []))
        if self._nodes[index].get("tag") == "a":
            return _prompt_text(" ".join(self._nodes[index].get("_text_parts") or []))
        if attrs.get("placeholder"):
            return _prompt_text(attrs["placeholder"])
        return ""

    def _bind_label_control(self, tag: str, attrs: dict[str, str]) -> None:
        if tag == "label":
            return
        control_role = attrs.get("role") or _implicit_role(tag, attrs)
        control_type = attrs.get("type") or control_role or tag
        if not control_type and not control_role:
            return
        for label_index in self._open_labels:
            if 0 <= label_index < len(self._nodes):
                if control_type and not self._nodes[label_index].get("_control_type"):
                    self._nodes[label_index]["_control_type"] = control_type
                if control_role and not self._nodes[label_index].get("_control_role"):
                    self._nodes[label_index]["_control_role"] = control_role


def _implicit_role(tag: str, attrs: dict[str, str]) -> str:
    tag_norm = (tag or "").strip().lower()
    input_type = (attrs.get("type") or "").strip().lower()
    if tag_norm == "button":
        return "button"
    if tag_norm == "a":
        return "link"
    if tag_norm == "textarea":
        return "textbox"
    if tag_norm == "select":
        return "combobox"
    if tag_norm == "input":
        if input_type in {"checkbox"}:
            return "checkbox"
        if input_type in {"radio"}:
            return "radio"
        if input_type in {"submit", "button"}:
            return "button"
        return "textbox"
    return ""


def _prompt_text(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return " ".join(raw.split())
