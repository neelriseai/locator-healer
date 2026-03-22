"""Compact prompt DSL builder for LLM fallback reasoning."""

from __future__ import annotations

from typing import Any

from xpath_healer.core.models import BuildInput
from xpath_healer.utils.text import normalize_text, safe_join


def build_prompt_dsl(
    inp: BuildInput,
    dom_signature: str,
    context_candidates: list[dict[str, Any]],
    dom_context: list[dict[str, Any]],
    deep_graph: bool = False,
    prefer_actionable: bool = False,
) -> str:
    lines: list[str] = []
    # Symbol DSL (compact, deterministic, low-token format):
    # E=element, PG=page, FT=field_type, F=failed locator, A=attributes,
    # P=parent/container hint, G=graph relations, C=context candidates, D=dom signature.
    lines.append(f"E {normalize_text(inp.element_name) or 'unknown'}")
    lines.append(f"PG {normalize_text(inp.page_name) or 'unknown'}")
    lines.append(f"FT {normalize_text(inp.field_type) or 'generic'}")
    lines.append(f"F {_compact_locator(inp.fallback.to_dict())}")
    lines.append(f"A {_compact_attr_tokens(inp)}")
    lines.append(f"P {_compact_parent_hint(inp, context_candidates)}")
    lines.extend(_graph_hint_lines(inp))

    lines.append("C")
    for idx, item in enumerate(context_candidates[:5], start=1):
        locator = _candidate_locator_line(item)
        score = item.get("rerank_score")
        if score is None:
            lines.append(f"{idx} {locator}")
        else:
            lines.append(f"{idx} {locator} S={float(score):.4f}")

    lines.append("H")
    for idx, item in enumerate(dom_context[:8], start=1):
        lines.append(f"{idx} {_dom_entity_line(item)}")

    lines.append(f"D {_compact_dom(dom_signature, limit=540 if deep_graph else 220)}")
    if deep_graph:
        lines.append("GD on")
    rules = [
        "R prefer stable attrs; prefer css/role when unique; avoid absolute/deep-index xpath; max 5",
        "R stay grounded in C, H and D; if evidence weak set needs_more_context=true",
        "R role candidates must use value as role only; put accessible name and exact in options",
        "R for checkbox/radio/switch: PREFER visible icon/svg/label/wrapper over hidden native input[type=checkbox/radio]",
        "R actionability required: every candidate must target a visible+interactable element; never suggest input[type=hidden]",
    ]
    if prefer_actionable:
        rules.append(
            "R STRICT ACTIONABILITY: prior attempt failed not_visible; shift ALL candidates to visible wrapper/icon/label; "
            "penalise any pure input[type=checkbox] or input[type=radio] selector with confidence<=0.3"
        )
    rules.append(
        "O JSON only: [{\"kind\":\"css|xpath|role|text|pw\",\"value\":\"...\",\"options\":{},\"confidence\":0.0,\"reason\":\"...\",\"needs_more_context\":false}]"
    )
    lines.extend(rules)
    return "\n".join(lines).strip()


def _compact_dom(dom_snippet: str, limit: int = 1200) -> str:
    text = " ".join((dom_snippet or "").split())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _compact_locator(locator_payload: dict[str, Any]) -> str:
    kind = str(locator_payload.get("kind") or "")
    value = str(locator_payload.get("value") or "")
    return f"{kind}={value}"


def _compact_attr_tokens(inp: BuildInput) -> str:
    tokens: list[str] = [f"FT={normalize_text(inp.field_type)}"]
    if inp.intent.label:
        tokens.append(f'LBL="{inp.intent.label}"')
    if inp.intent.text:
        tokens.append(f'TXT="{inp.intent.text}"')
    if inp.intent.axis_hint:
        tokens.append(f"AX={normalize_text(inp.intent.axis_hint)}")
    tokens.append(f"OCC={inp.intent.occurrence}")

    preferred_keys = (
        "id",
        "data-testid",
        "aria-label",
        "name",
        "formcontrolname",
        "placeholder",
        "role",
        "type",
        "href",
    )
    key_symbol = {
        "id": "ID",
        "data-testid": "TID",
        "aria-label": "AR",
        "name": "NM",
        "formcontrolname": "FCN",
        "placeholder": "PH",
        "role": "RL",
        "type": "TP",
        "href": "HF",
    }
    for key in preferred_keys:
        value = inp.vars.get(key)
        if value:
            symbol = key_symbol.get(key, key.upper())
            tokens.append(f'{symbol}="{value}"')

    tag_hint = normalize_text(inp.vars.get("tag"))
    if tag_hint:
        tokens.append(f"T={tag_hint}")
    elif inp.field_type.casefold() in {"button", "link", "textbox", "input", "checkbox"}:
        inferred = {
            "button": "button",
            "link": "a",
            "textbox": "input",
            "input": "input",
            "checkbox": "input",
        }[inp.field_type.casefold()]
        tokens.append(f"T={inferred}")
    return safe_join(tokens, sep=" ")


def _compact_parent_hint(inp: BuildInput, context_candidates: list[dict[str, Any]]) -> str:
    for key in ("container", "parent", "section", "group"):
        value = inp.vars.get(key)
        if value:
            return normalize_text(value)
    if context_candidates:
        candidate = context_candidates[0]
        for key in ("page_name", "element_name"):
            value = candidate.get(key)
            if value:
                return f"{normalize_text(str(candidate.get('page_name') or inp.page_name))}.{normalize_text(str(value))}"
    return normalize_text(inp.page_name)


def _candidate_locator_line(candidate: dict[str, Any]) -> str:
    for key in ("locator", "last_good_locator", "robust_locator"):
        value = candidate.get(key)
        if isinstance(value, dict) and value.get("kind") and value.get("value"):
            return _compact_locator(value)

    kind = candidate.get("kind")
    value = candidate.get("value")
    if kind and value:
        return f"{kind}={value}"

    page = normalize_text(str(candidate.get("page_name") or ""))
    element = normalize_text(str(candidate.get("element_name") or ""))
    return f"meta={page}.{element}".strip(".")


def _dom_entity_line(entity: dict[str, Any]) -> str:
    attrs = entity.get("attrs") if isinstance(entity.get("attrs"), dict) else {}
    parts = [f"tag={normalize_text(str(entity.get('tag') or ''))}"]
    role = normalize_text(str(entity.get("role") or ""))
    if role:
        parts.append(f"role={role}")
    control_type = normalize_text(str(entity.get("control_type") or ""))
    if control_type:
        parts.append(f"control={control_type}")
    label = _prompt_text(entity.get("label"))
    if label:
        parts.append(f'label="{label}"')
    text = _prompt_text(entity.get("text"))
    if text and text != label:
        parts.append(f'text="{text}"')
    for key in ("id", "name", "placeholder", "type", "data-testid", "aria-label", "href"):
        value = _prompt_text(attrs.get(key))
        if value:
            token = key.replace("-", "_")
            parts.append(f'{token}="{value}"')
    return safe_join(parts, sep=" ")


def _graph_hint_lines(inp: BuildInput) -> list[str]:
    lines: list[str] = []
    node_hint = _node_hint(inp)
    if node_hint:
        lines.append(f"G NODE {node_hint}")

    parent_hint = ""
    for key in ("container", "parent", "section", "group", "ancestor"):
        value = inp.vars.get(key)
        if value:
            parent_hint = normalize_text(value)
            break
    if parent_hint:
        lines.append(f"G PARENT {parent_hint}")

    left = _first_hint(inp, ("left", "left_sibling", "before", "preceding", "prev", "previous"))
    if left:
        lines.append(f"G LEFT {left}")

    right = _first_hint(inp, ("right", "right_sibling", "after", "following", "next"))
    if right:
        lines.append(f"G RIGHT {right}")

    anchor = normalize_text(inp.intent.label or inp.intent.text or inp.vars.get("anchor"))
    if anchor:
        lines.append(f"G ANCHOR {anchor}")
    return lines


def _node_hint(inp: BuildInput) -> str:
    tag = normalize_text(inp.vars.get("tag"))
    id_like = inp.vars.get("id") or inp.vars.get("data-testid") or inp.vars.get("name")
    node = tag
    if id_like:
        suffix = normalize_text(id_like).replace(" ", "-")
        if node:
            return f"{node}#{suffix}"
        return f"#{suffix}"
    return node


def _first_hint(inp: BuildInput, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = inp.vars.get(key)
        if value:
            return normalize_text(value)
    return ""


def _prompt_text(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return " ".join(raw.split())
