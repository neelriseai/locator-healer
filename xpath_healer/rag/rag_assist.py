"""Optional RAG stage that proposes locator specs (must be validated)."""

from __future__ import annotations

import json
import re
from typing import Any

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.rag.embedder import Embedder
from xpath_healer.rag.llm import LLM
from xpath_healer.rag.prompt_builder import build_dom_signature, build_prompt_payload, extract_dom_context
from xpath_healer.rag.retriever import Retriever


class RagAssist:
    def __init__(
        self,
        embedder: Embedder,
        retriever: Retriever,
        llm: LLM,
        graph_deep_default: bool = False,
        min_confidence_for_accept: float = 0.65,
        prompt_top_n: int = 3,
    ) -> None:
        self.embedder = embedder
        self.retriever = retriever
        self.llm = llm
        self.graph_deep_default = bool(graph_deep_default)
        self.min_confidence_for_accept = min(max(float(min_confidence_for_accept), 0.0), 1.0)
        self.prompt_top_n = max(1, int(prompt_top_n))
        self.last_telemetry: dict[str, Any] | None = None

    async def suggest(
        self,
        inp: BuildInput,
        dom_snippet: str,
        top_k: int = 5,
        deep_graph: bool | None = None,
        prefer_actionable: bool = False,
    ) -> list[LocatorSpec]:
        use_deep_graph = self.graph_deep_default if deep_graph is None else bool(deep_graph)
        use_actionable = prefer_actionable or self._prefer_actionable(inp)
        dom_signature = build_dom_signature(dom_snippet, deep_graph=use_deep_graph)
        query = self._build_query(inp, dom_signature)
        embedding = await self.embedder.embed_text(query)
        dom_context = self._rank_dom_context(
            inp,
            extract_dom_context(dom_snippet, deep_graph=use_deep_graph),
            limit=16 if use_deep_graph else 10,
        )
        if hasattr(self.retriever, "set_query_context"):
            try:
                self.retriever.set_query_context(  # type: ignore[attr-defined]
                    app_id=inp.app_id,
                    page_name=inp.page_name,
                    field_type=inp.field_type,
                )
            except Exception:
                pass
        retrieve_k = min(max(top_k * 20, 50), 200)
        retrieved_context = await self.retriever.retrieve(embedding, top_k=retrieve_k)
        dom_seed_context = self._build_dom_seed_context(inp, dom_context)
        raw_context = list(retrieved_context) + dom_seed_context
        top_n = min(self.prompt_top_n, max(1, top_k))
        context = self._rerank_context(raw_context, top_n=top_n, query_tokens=self._query_tokens(inp))
        payload = build_prompt_payload(
            inp=inp,
            dom_snippet=dom_snippet,
            context_candidates=context,
            dom_context=dom_context,
            deep_graph=use_deep_graph,
            prefer_actionable=use_actionable,
        )
        payload_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        dsl_prompt = str(payload.get("dsl_prompt") or "")
        context_json = json.dumps(payload.get("context") or [], ensure_ascii=True, separators=(",", ":"))
        dom_sig = str(payload.get("dom_signature") or "")
        self.last_telemetry = {
            "raw_context_count": len(retrieved_context),
            "prompt_context_count": len(context),
            "dom_seed_count": len(dom_seed_context),
            "retrieve_k": retrieve_k,
            "top_k": int(top_k),
            "prompt_top_n": int(top_n),
            "query_chars": len(query),
            "dom_signature_chars": len(dom_sig),
            "dsl_prompt_chars": len(dsl_prompt),
            "context_json_chars": len(context_json),
            "dom_context_count": len(payload.get("dom_context") or []),
            "payload_chars": len(payload_json),
            "embedding_dims": len(embedding),
            "prefer_actionable": bool(use_actionable),
        }
        rules = payload.setdefault("rules", {})
        rules["prefer_compact_dsl"] = True
        rules["max_candidates"] = max(1, min(5, top_k))
        rules["min_confidence_for_accept"] = self.min_confidence_for_accept
        if use_actionable:
            rules["require_actionable"] = True
            rules["avoid_hidden_native_inputs_for_toggles"] = True
        raw = await self.llm.suggest_locators(payload)
        allowed_context = self._allowed_context_keys(context)
        suggestions = self._parse_suggestions(
            raw,
            allowed_context=allowed_context,
            min_confidence_for_accept=self.min_confidence_for_accept,
            field_type=inp.field_type,
            prefer_actionable=use_actionable,
        )
        if top_k > 0:
            return suggestions[:top_k]
        return suggestions

    @staticmethod
    def _build_query(inp: BuildInput, dom_signature: str) -> str:
        tags = []
        for key in (
            "id",
            "data-testid",
            "name",
            "role",
            "type",
            "placeholder",
            "target",
            "container",
            "parent",
            "section",
            "anchor",
            "class",
        ):
            value = str(inp.vars.get(key) or "").strip()
            if value:
                tags.append(f"{key}={value}")
        label = str(inp.intent.label or inp.intent.text or "").strip()
        parent = str(inp.vars.get("parent") or inp.vars.get("container") or inp.page_name).strip()
        parts = [
            f"app={inp.app_id}",
            f"page={inp.page_name}",
            f"element={inp.element_name}",
            f"field_type={inp.field_type}",
            f'label="{label}"' if label else "",
            f"parent={parent}" if parent else "",
            ("attrs=" + " ".join(tags)) if tags else "",
            f"dom_sig={dom_signature[:320]}",
        ]
        return " | ".join(part for part in parts if part)

    @staticmethod
    def _prefer_actionable(inp: BuildInput) -> bool:
        field_type = str(inp.field_type or "").strip().casefold()
        if field_type in {"checkbox", "radio", "switch"}:
            return True
        target = str(inp.vars.get("target") or "").strip().casefold()
        return target in {"icon", "proxy", "wrapper", "label", "toggle"}

    @staticmethod
    def _rerank_context(
        context: list[dict[str, Any]],
        top_n: int,
        query_tokens: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        tokens = {item.casefold() for item in (query_tokens or set()) if item}
        scored: list[tuple[float, int, dict[str, Any]]] = []
        for idx, item in enumerate(context):
            if not isinstance(item, dict):
                continue
            vector_similarity = float(item.get("similarity") or item.get("vector_similarity") or item.get("score") or 0.0)
            structural_similarity = float(item.get("structural_similarity") or 0.0)
            quality = item.get("quality_metrics") if isinstance(item.get("quality_metrics"), dict) else {}
            stability = float(item.get("stability_score") or quality.get("stability_score") or 0.0)
            uniqueness = float(item.get("uniqueness_score") or quality.get("uniqueness_score") or 0.0)
            token_overlap = RagAssist._token_overlap(tokens, item)
            rerank = (
                0.40 * vector_similarity
                + 0.22 * structural_similarity
                + 0.20 * stability
                + 0.10 * uniqueness
                + 0.08 * token_overlap
            )
            enriched = dict(item)
            enriched["rerank_score"] = round(rerank, 6)
            enriched["token_overlap"] = round(token_overlap, 6)
            scored.append((rerank, -idx, enriched))

        scored.sort(reverse=True)
        return [entry for _, _, entry in scored[: max(1, top_n)]]

    @staticmethod
    def _query_tokens(inp: BuildInput) -> set[str]:
        out: set[str] = set()
        seeds = [
            inp.app_id,
            inp.page_name,
            inp.element_name,
            inp.field_type,
            inp.intent.label,
            inp.intent.text,
            inp.vars.get("id"),
            inp.vars.get("data-testid"),
            inp.vars.get("name"),
            inp.vars.get("placeholder"),
            inp.vars.get("role"),
            inp.vars.get("type"),
            inp.vars.get("container"),
            inp.vars.get("parent"),
            inp.vars.get("section"),
            inp.vars.get("target"),
            inp.vars.get("anchor"),
            inp.vars.get("class"),
        ]
        for raw in seeds:
            if not raw:
                continue
            text = str(raw).strip().casefold()
            if not text:
                continue
            for token in re.split(r"[^a-z0-9:_-]+", text):
                tok = token.strip()
                if len(tok) >= 2:
                    out.add(tok)
        return out

    @staticmethod
    def _token_overlap(query_tokens: set[str], candidate: dict[str, Any]) -> float:
        if not query_tokens:
            return 0.0
        candidate_tokens: set[str] = set()
        for key in ("element_name", "field_type", "page_name", "source", "chunk_text"):
            value = candidate.get(key)
            if not value:
                continue
            for token in re.split(r"[^a-z0-9:_-]+", str(value).casefold()):
                if len(token) >= 2:
                    candidate_tokens.add(token)
        metadata = candidate.get("metadata")
        if isinstance(metadata, dict):
            for key in ("field_type", "tag", "component_kind", "prompt_compact_text"):
                value = metadata.get(key)
                if not value:
                    continue
                for token in re.split(r"[^a-z0-9:_-]+", str(value).casefold()):
                    if len(token) >= 2:
                        candidate_tokens.add(token)
            fp = metadata.get("fingerprint_tokens")
            if isinstance(fp, list):
                for item in fp:
                    for token in re.split(r"[^a-z0-9:_-]+", str(item).casefold()):
                        if len(token) >= 2:
                            candidate_tokens.add(token)
        if not candidate_tokens:
            return 0.0
        overlap = query_tokens & candidate_tokens
        if not overlap:
            return 0.0
        return len(overlap) / float(len(query_tokens))

    @staticmethod
    def _allowed_context_keys(context: list[dict[str, Any]]) -> set[str]:
        allowed: set[str] = set()
        for item in context:
            if not isinstance(item, dict):
                continue
            locator = item.get("locator")
            if isinstance(locator, dict) and locator.get("kind") and locator.get("value"):
                allowed.add(RagAssist._locator_ground_key(locator))
        return allowed

    @staticmethod
    def _parse_suggestions(
        raw: list[dict[str, Any]],
        allowed_context: set[str] | None = None,
        min_confidence_for_accept: float = 0.65,
        field_type: str = "",
        prefer_actionable: bool = False,
    ) -> list[LocatorSpec]:
        allowed = {item.casefold() for item in (allowed_context or set()) if item}
        dedup: dict[str, tuple[float, int, LocatorSpec]] = {}
        for idx, item in enumerate(raw):
            try:
                normalized = RagAssist._normalize_candidate_payload(item)
                kind = str(normalized.get("kind") or "").strip()
                value = str(normalized.get("value") or "").strip()
                if not kind or not value:
                    continue
                confidence = RagAssist._coerce_confidence(normalized.get("confidence"))
                reason = str(normalized.get("reason") or "").strip()
                options = dict(normalized.get("options") or {})
                needs_more_context = bool(normalized.get("needs_more_context") or options.pop("needs_more_context", False))
                candidate = LocatorSpec(
                    kind=kind,
                    value=value,
                    options=options,
                    scope=LocatorSpec.from_dict(normalized["scope"]) if normalized.get("scope") else None,
                )
                if RagAssist._is_weak_locator(candidate):
                    continue

                grounded = RagAssist._is_grounded(candidate, allowed)
                red_flags = RagAssist._hallucination_red_flags(
                    candidate,
                    reason=reason,
                    confidence=confidence,
                    grounded=grounded,
                    min_confidence=min_confidence_for_accept,
                    has_context=bool(allowed),
                )
                if len(red_flags) >= 2:
                    continue

                candidate.options["_llm_confidence"] = confidence
                if reason:
                    candidate.options["_llm_reason"] = reason[:240]
                if needs_more_context:
                    candidate.options["_llm_needs_more_context"] = True
                if red_flags:
                    candidate.options["_llm_red_flags"] = red_flags
                if allowed:
                    candidate.options["_grounded_in_context"] = grounded

                stable = RagAssist._dedupe_key(candidate)
                effective_confidence = confidence
                if allowed and not grounded:
                    effective_confidence = max(0.0, effective_confidence - 0.10)
                # Penalise pure native-input selectors for toggle field types: custom UI
                # libraries typically CSS-hide the native input and render a visible icon/
                # wrapper instead.  Targeting the raw input will fail not_visible at runtime.
                if RagAssist._is_native_toggle_selector(candidate, field_type):
                    penalty = 0.35 if prefer_actionable else 0.15
                    effective_confidence = max(0.0, effective_confidence - penalty)
                    candidate.options["_native_toggle_penalty"] = True
                rank = (effective_confidence, -idx)
                previous = dedup.get(stable)
                if previous is None or rank > (previous[0], previous[1]):
                    dedup[stable] = (effective_confidence, -idx, candidate)
            except Exception:
                continue

        ordered = sorted(dedup.values(), key=lambda item: (item[0], item[1]), reverse=True)
        return [candidate for _, _, candidate in ordered]

    @staticmethod
    def _normalize_candidate_payload(item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        kind = str(normalized.get("kind") or "").strip().casefold()
        value = str(normalized.get("value") or "").strip()
        options = dict(normalized.get("options") or {})

        inferred_kind, stripped_value = RagAssist._strip_kind_prefix(kind, value)
        if inferred_kind:
            kind = inferred_kind
            value = stripped_value

        if kind == "role":
            role_value, role_options = RagAssist._parse_compact_role_value(value)
            if role_value:
                kind = "role"
                value = role_value
                merged = dict(role_options)
                merged.update(options)
                options = merged

        normalized["kind"] = kind
        normalized["value"] = value
        normalized["options"] = options
        return normalized

    @staticmethod
    def _strip_kind_prefix(kind: str, value: str) -> tuple[str | None, str]:
        raw = (value or "").strip()
        for prefix in ("css", "xpath", "role", "text", "pw"):
            token = f"{prefix}="
            if raw.casefold().startswith(token):
                return prefix, raw[len(token):].strip()
        return (kind or None), raw

    @staticmethod
    def _parse_compact_role_value(value: str) -> tuple[str | None, dict[str, Any]]:
        raw = (value or "").strip()
        match = re.fullmatch(r"(?P<role>[a-z][a-z0-9_-]*)(?P<filters>(\[[^\]]+\])*)", raw, flags=re.IGNORECASE)
        if not match:
            return None, {}
        role = str(match.group("role") or "").strip().casefold()
        filters = str(match.group("filters") or "")
        if not filters:
            return role, {}

        options: dict[str, Any] = {}
        for content in re.findall(r"\[([^\]]+)\]", filters):
            if "=" not in content:
                continue
            key, raw_value = content.split("=", 1)
            key_norm = str(key).strip().casefold()
            parsed_value = RagAssist._parse_scalar(raw_value)
            if key_norm in {"name", "exact", "checked", "disabled", "pressed", "selected"}:
                options[key_norm] = parsed_value
        return role, options

    @staticmethod
    def _parse_scalar(raw_value: str) -> Any:
        text = str(raw_value or "").strip()
        if not text:
            return ""
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
            return text[1:-1]
        lowered = text.casefold()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return int(text)
        except Exception:
            return text

    @staticmethod
    def _is_weak_locator(locator: LocatorSpec) -> bool:
        value = (locator.value or "").strip().casefold()
        if locator.kind == "css":
            if value in {"*", "html", "body", "div", "span", "a", "p"}:
                return True
            if value.count(":nth-") >= 3 and "[" not in value and "#" not in value:
                return True
            return False
        if locator.kind == "xpath":
            if value in {"//*", "//html", "/html[1]"}:
                return True
            if value.startswith("/html"):
                indexed_steps = re.findall(r"/[a-z0-9:_-]+\[\d+\]", value)
                stable_attr = any(
                    token in value
                    for token in ("@id=", "@data-testid", "@name=", "@aria-label", "@role=", "@placeholder", "@type=")
                )
                if len(indexed_steps) >= 3 and not stable_attr:
                    return True
            return False
        return False

    @staticmethod
    def _is_native_toggle_selector(locator: LocatorSpec, field_type: str) -> bool:
        """Return True when the locator targets a native checkbox/radio input directly.

        Custom UI libraries (DemoQA, Material, Ant-design, etc.) CSS-hide the native
        input and render a visible icon/wrapper. Pointing directly at the raw input
        reliably fails the not_visible validation check.  We apply a confidence penalty
        so that wrapper/label/icon alternatives rank higher.
        """
        ft = (field_type or "").strip().casefold()
        if ft not in {"checkbox", "radio", "switch"}:
            return False
        value = (locator.value or "").strip()
        if locator.kind == "css":
            # Patterns like: input[type="checkbox"], input[type='radio'],
            # input[type=checkbox], input.some-class (tag=input with no wrapper context)
            value_lower = value.casefold()
            if re.match(r'^input\[type\s*=\s*["\']?(checkbox|radio)["\']?\]', value_lower):
                return True
            # Bare input tag selector (no ancestor path) is also suspect for toggle types
            if re.match(r'^input(\.|#|\[|$)', value_lower) and ">" not in value and " " not in value.strip():
                return True
        if locator.kind == "xpath":
            value_lower = value.casefold()
            if re.search(r'//input\[@type\s*=\s*["\']?(checkbox|radio)["\']?\]', value_lower):
                return True
        return False

    @staticmethod
    def _is_grounded(locator: LocatorSpec, allowed_context: set[str]) -> bool:
        if not allowed_context:
            return True
        return RagAssist._locator_ground_key(locator) in allowed_context

    @staticmethod
    def _hallucination_red_flags(
        locator: LocatorSpec,
        reason: str,
        confidence: float,
        grounded: bool,
        min_confidence: float,
        has_context: bool,
    ) -> list[str]:
        flags: list[str] = []
        if confidence < min_confidence:
            flags.append("low_confidence")
        if not reason:
            flags.append("missing_reason")
        elif not RagAssist._grounded_reason(reason):
            flags.append("vague_reason")
        if has_context and not grounded:
            flags.append("outside_candidate_universe")
        if RagAssist._is_unstable_pattern(locator):
            flags.append("unstable_pattern")
        return flags

    @staticmethod
    def _grounded_reason(reason: str) -> bool:
        reason_norm = reason.casefold()
        evidence_tokens = (
            "id",
            "data-testid",
            "aria",
            "name",
            "placeholder",
            "label",
            "role",
            "anchor",
            "container",
            "unique",
        )
        return any(token in reason_norm for token in evidence_tokens)

    @staticmethod
    def _is_unstable_pattern(locator: LocatorSpec) -> bool:
        value = (locator.value or "").strip().casefold()
        if locator.kind == "css":
            if value in {"div", "span"}:
                return True
            if value.count(":nth-child(") >= 2:
                return True
            return False
        if locator.kind == "xpath":
            if value.startswith("/html"):
                return True
            if re.search(r"//[a-z0-9:_-]+\[\d+\](/[a-z0-9:_-]+\[\d+\]){2,}", value):
                return True
            return False
        return False

    @staticmethod
    def _coerce_confidence(raw: Any) -> float:
        try:
            value = float(raw)
        except Exception:
            value = 0.5
        return min(max(value, 0.0), 1.0)

    @staticmethod
    def _dedupe_key(locator: LocatorSpec) -> str:
        return f"{locator.kind}::{locator.value}::{locator.scope.stable_hash() if locator.scope else ''}"

    @staticmethod
    def _locator_ground_key(locator: LocatorSpec | dict[str, Any]) -> str:
        if isinstance(locator, LocatorSpec):
            kind = locator.kind
            value = locator.value
            options = dict(locator.options or {})
        else:
            kind = str(locator.get("kind") or "").strip().casefold()
            value = str(locator.get("value") or "").strip()
            options = dict(locator.get("options") or {})
        if kind == "role":
            name = _normalize_ground_value(options.get("name"))
            exact = str(bool(options.get("exact", False))).lower()
            return f"{kind}::{value.casefold()}::name={name}::exact={exact}"
        if kind == "text":
            exact = str(bool(options.get("exact", False))).lower()
            return f"{kind}::{value.casefold()}::exact={exact}"
        return f"{kind}::{value}".casefold()

    def _build_dom_seed_context(self, inp: BuildInput, dom_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
        query_tokens = self._query_tokens(inp)
        out: list[dict[str, Any]] = []
        for index, entity in enumerate(dom_context):
            if not isinstance(entity, dict):
                continue
            attrs = entity.get("attrs") if isinstance(entity.get("attrs"), dict) else {}
            label = str(entity.get("label") or "")
            text = str(entity.get("text") or "")
            tag = str(entity.get("tag") or "")
            role = str(entity.get("role") or "")
            field_type = self._entity_field_type(tag, role, attrs)
            compact_text = " ".join(part for part in [label, text, attrs.get("placeholder"), attrs.get("name")] if part)
            for locator in self._entity_locators(entity):
                out.append(
                    {
                        "app_id": inp.app_id,
                        "page_name": inp.page_name,
                        "element_name": f"dom_entity_{index}",
                        "field_type": field_type,
                        "locator": locator.to_dict(),
                        "similarity": self._dom_seed_similarity(inp, field_type, label, text, attrs, query_tokens),
                        "structural_similarity": self._field_type_similarity(inp.field_type, field_type),
                        "quality_metrics": {"stability_score": self._dom_seed_stability(locator), "uniqueness_score": 0.60},
                        "metadata": {"prompt_compact_text": compact_text[:240]},
                    }
                )
        return out

    def _rank_dom_context(self, inp: BuildInput, dom_context: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        query_tokens = self._query_tokens(inp)
        scored: list[tuple[float, int, dict[str, Any]]] = []
        for index, entity in enumerate(dom_context):
            if not isinstance(entity, dict):
                continue
            attrs = entity.get("attrs") if isinstance(entity.get("attrs"), dict) else {}
            label = str(entity.get("label") or "")
            text = str(entity.get("text") or "")
            tag = str(entity.get("tag") or "")
            role = str(entity.get("role") or "")
            field_type = self._entity_field_type(tag, role, attrs)
            similarity = self._dom_seed_similarity(inp, field_type, label, text, attrs, query_tokens)
            structural = self._field_type_similarity(inp.field_type, field_type)
            label_bonus = 0.15 if _normalize_ground_value(label or text) else 0.0
            score = (0.60 * structural) + (0.40 * similarity) + label_bonus
            scored.append((score, -index, entity))
        scored.sort(reverse=True)
        return [entity for _, _, entity in scored[: max(1, limit)]]

    @staticmethod
    def _entity_field_type(tag: str, role: str, attrs: dict[str, Any]) -> str:
        role_norm = (role or "").strip().casefold()
        tag_norm = (tag or "").strip().casefold()
        type_norm = str(attrs.get("type") or "").strip().casefold()
        class_norm = str(attrs.get("class") or "").strip().casefold()
        if any(token in class_norm for token in ("checkbox", "rct-checkbox")):
            return "checkbox"
        if "radio" in class_norm:
            return "radio"
        if any(token in class_norm for token in ("switch", "toggle")):
            return "switch"
        if role_norm:
            return role_norm
        if tag_norm == "textarea":
            return "textbox"
        if tag_norm == "select":
            return "combobox"
        if tag_norm == "a":
            return "link"
        if tag_norm == "button":
            return "button"
        if tag_norm == "input" and type_norm in {"checkbox", "radio"}:
            return type_norm
        if tag_norm == "input" and type_norm in {"submit", "button"}:
            return "button"
        if tag_norm == "input":
            return "textbox"
        return tag_norm or "generic"

    @staticmethod
    def _entity_locators(entity: dict[str, Any]) -> list[LocatorSpec]:
        attrs = entity.get("attrs") if isinstance(entity.get("attrs"), dict) else {}
        out: list[LocatorSpec] = []
        for key in ("data-testid", "id", "name", "placeholder", "aria-label", "href"):
            value = str(attrs.get(key) or "").strip()
            if value:
                out.append(LocatorSpec(kind="css", value=f'[{key}="{value}"]'))
        label_for = str(attrs.get("for") or "").strip()
        if label_for:
            out.append(LocatorSpec(kind="css", value=f'label[for="{label_for}"]'))
        tag = str(entity.get("tag") or "").strip().casefold()
        class_raw = str(attrs.get("class") or "").strip()
        class_tokens = [token for token in class_raw.split() if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*", token)]
        class_candidates = [
            token
            for token in class_tokens
            if any(marker in token.casefold() for marker in ("checkbox", "radio", "switch", "toggle", "icon", "btn"))
        ][:2]
        for token in class_candidates:
            if tag:
                out.append(LocatorSpec(kind="css", value=f'{tag}[class*="{token}"]'))
            out.append(LocatorSpec(kind="css", value=f'[class*="{token}"]'))
        role = str(entity.get("role") or "").strip().casefold()
        label = str(entity.get("label") or "").strip()
        text = str(entity.get("text") or "").strip()
        if role:
            options: dict[str, Any] = {}
            if label:
                options["name"] = label
                options["exact"] = False
            elif text:
                options["name"] = text
                options["exact"] = False
            out.append(LocatorSpec(kind="role", value=role, options=options))
        if text:
            out.append(LocatorSpec(kind="text", value=text, options={"exact": False}))
        dedup: dict[str, LocatorSpec] = {}
        for locator in out:
            dedup[RagAssist._dedupe_key(locator)] = locator
        return list(dedup.values())

    @staticmethod
    def _dom_seed_similarity(
        inp: BuildInput,
        field_type: str,
        label: str,
        text: str,
        attrs: dict[str, Any],
        query_tokens: set[str],
    ) -> float:
        candidate_tokens: set[str] = set()
        for raw in [
            field_type,
            label,
            text,
            attrs.get("name"),
            attrs.get("placeholder"),
            attrs.get("aria-label"),
            attrs.get("class"),
            attrs.get("id"),
            attrs.get("data-testid"),
        ]:
            candidate_tokens.update(_token_set(raw))
        if not candidate_tokens or not query_tokens:
            return 0.0
        overlap = len(candidate_tokens & query_tokens) / float(len(query_tokens))
        return min(1.0, 0.35 + overlap)

    @staticmethod
    def _field_type_similarity(expected: str, actual: str) -> float:
        expected_norm = (expected or "").strip().casefold()
        actual_norm = (actual or "").strip().casefold()
        if not expected_norm or not actual_norm:
            return 0.0
        if expected_norm == actual_norm:
            return 1.0
        aliases = {
            "textbox": {"input", "textbox"},
            "input": {"input", "textbox"},
            "button": {"button"},
            "link": {"link"},
            "checkbox": {"checkbox", "switch", "toggle"},
            "radio": {"radio", "toggle"},
            "dropdown": {"combobox", "select", "dropdown"},
            "combobox": {"combobox", "select", "dropdown"},
            "text": {"text", "gridcell", "cell", "generic"},
        }
        expected_group = aliases.get(expected_norm, {expected_norm})
        return 0.75 if actual_norm in expected_group else 0.1

    @staticmethod
    def _dom_seed_stability(locator: LocatorSpec) -> float:
        value = (locator.value or "").strip()
        if locator.kind == "role":
            return 0.90
        if locator.kind == "text":
            return 0.68
        if any(token in value for token in ('[data-testid=', '[id=', '[name=', '[aria-label=', '[placeholder=')):
            return 0.86
        if '[href=' in value:
            return 0.76
        return 0.60


def _token_set(raw: Any) -> set[str]:
    out: set[str] = set()
    text = str(raw or "").strip().casefold()
    if not text:
        return out
    for token in re.split(r"[^a-z0-9:_-]+", text):
        piece = token.strip()
        if len(piece) >= 2:
            out.add(piece)
    return out


def _normalize_ground_value(raw: Any) -> str:
    return " ".join(str(raw or "").strip().casefold().split())
