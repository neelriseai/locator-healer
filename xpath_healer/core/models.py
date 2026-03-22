"""Core data models for selector healing."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from xpath_healer.utils.text import coerce_bool


SUPPORTED_LOCATOR_KINDS = {"css", "xpath", "role", "text", "pw"}
INTERACTIVE_FIELD_TYPES = {
    "button",
    "link",
    "textbox",
    "input",
    "dropdown",
    "combobox",
    "checkbox",
    "radio",
}


@dataclass(slots=True)
class LocatorSpec:
    kind: str
    value: str
    options: dict[str, Any] = field(default_factory=dict)
    scope: LocatorSpec | None = None

    def __post_init__(self) -> None:
        self.kind = (self.kind or "").strip().lower()
        if self.kind not in SUPPORTED_LOCATOR_KINDS:
            raise ValueError(f"Unsupported locator kind: {self.kind}")
        self.value = self.value or ""

    def __str__(self) -> str:
        base = f"{self.kind}:{self.value}"
        if self.options:
            return f"{base} options={self.options}"
        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "options": self.options,
            "scope": self.scope.to_dict() if self.scope else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LocatorSpec:
        scope = payload.get("scope")
        return cls(
            kind=str(payload["kind"]),
            value=str(payload["value"]),
            options=dict(payload.get("options") or {}),
            scope=cls.from_dict(scope) if scope else None,
        )

    def stable_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

@dataclass(slots=True)
class HealingHints:
    attr_priority_order: list[str] = field(default_factory=list)
    threshold: float | None = None
    visibility_pref: bool = True
    aliases: dict[str, list[str]] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)
    allow_position_fallback: bool = False
    strict_single_match: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "attr_priority_order": self.attr_priority_order,
            "threshold": self.threshold,
            "visibility_pref": self.visibility_pref,
            "aliases": self.aliases,
            "defaults": self.defaults,
            "allow_position_fallback": self.allow_position_fallback,
            "strict_single_match": self.strict_single_match,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HealingHints:
        return cls(
            attr_priority_order=list(payload.get("attr_priority_order") or []),
            threshold=payload.get("threshold"),
            visibility_pref=coerce_bool(payload.get("visibility_pref"), True),
            aliases=dict(payload.get("aliases") or {}),
            defaults=dict(payload.get("defaults") or {}),
            allow_position_fallback=coerce_bool(payload.get("allow_position_fallback"), False),
            strict_single_match=coerce_bool(payload.get("strict_single_match"), True),
        )


@dataclass(slots=True)
class Intent:
    label: str | None = None
    text: str | None = None
    axis_hint: str | None = None
    match_mode: str = "exact"
    occurrence: int = 0
    allow_position: bool = False
    strict_single_match: bool | None = None
    label_locator: LocatorSpec | None = None
    geometry_tolerance: float = 8.0
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_vars(cls, vars_map: dict[str, str] | None) -> Intent:
        vars_map = vars_map or {}
        label = vars_map.get("label") or vars_map.get("label_text") or vars_map.get("name")
        text = vars_map.get("text") or vars_map.get("button_text") or label
        axis = vars_map.get("axisHint") or vars_map.get("axis_hint")
        occurrence = int(vars_map.get("occurrence", vars_map.get("index", "0")) or "0")
        match_mode = (vars_map.get("match_mode") or "exact").strip().lower()
        allow_position = coerce_bool(vars_map.get("allow_position"), False)
        strict_single = vars_map.get("strict_single_match")
        strict_single_match = None if strict_single is None else coerce_bool(strict_single, True)
        return cls(
            label=label,
            text=text,
            axis_hint=axis,
            match_mode=match_mode,
            occurrence=occurrence,
            allow_position=allow_position,
            strict_single_match=strict_single_match,
            metadata=dict(vars_map),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "text": self.text,
            "axis_hint": self.axis_hint,
            "match_mode": self.match_mode,
            "occurrence": self.occurrence,
            "allow_position": self.allow_position,
            "strict_single_match": self.strict_single_match,
            "label_locator": self.label_locator.to_dict() if self.label_locator else None,
            "geometry_tolerance": self.geometry_tolerance,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    reason_codes: list[str] = field(default_factory=list)
    matched_count: int = 0
    chosen_index: int | None = None
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        matched_count: int,
        chosen_index: int,
        reason_codes: list[str] | None = None,
        score: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> ValidationResult:
        return cls(
            ok=True,
            reason_codes=reason_codes or ["ok"],
            matched_count=matched_count,
            chosen_index=chosen_index,
            score=score,
            details=details or {},
        )

    @classmethod
    def fail(
        cls,
        reason_codes: list[str],
        matched_count: int = 0,
        details: dict[str, Any] | None = None,
    ) -> ValidationResult:
        return cls(ok=False, reason_codes=reason_codes, matched_count=matched_count, details=details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason_codes": self.reason_codes,
            "matched_count": self.matched_count,
            "chosen_index": self.chosen_index,
            "score": self.score,
            "details": self.details,
        }


@dataclass(slots=True)
class ElementSignature:
    tag: str
    stable_attrs: dict[str, str] = field(default_factory=dict)
    short_text: str = ""
    container_path: list[str] = field(default_factory=list)
    component_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "stable_attrs": self.stable_attrs,
            "short_text": self.short_text,
            "container_path": self.container_path,
            "component_kind": self.component_kind,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ElementSignature:
        return cls(
            tag=str(payload.get("tag") or ""),
            stable_attrs=dict(payload.get("stable_attrs") or {}),
            short_text=str(payload.get("short_text") or ""),
            container_path=list(payload.get("container_path") or []),
            component_kind=payload.get("component_kind"),
        )


@dataclass(slots=True)
class ElementMeta:
    app_id: str
    page_name: str
    element_name: str
    field_type: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    last_good_locator: LocatorSpec | None = None
    robust_locator: LocatorSpec | None = None
    strategy_id: str | None = None
    signature: ElementSignature | None = None
    hints: HealingHints | None = None
    locator_variants: dict[str, LocatorSpec] = field(default_factory=dict)
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    success_count: int = 0
    fail_count: int = 0

    def key(self) -> tuple[str, str, str]:
        return (self.app_id, self.page_name, self.element_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "app_id": self.app_id,
            "page_name": self.page_name,
            "element_name": self.element_name,
            "field_type": self.field_type,
            "last_good_locator": self.last_good_locator.to_dict() if self.last_good_locator else None,
            "robust_locator": self.robust_locator.to_dict() if self.robust_locator else None,
            "strategy_id": self.strategy_id,
            "signature": self.signature.to_dict() if self.signature else None,
            "hints": self.hints.to_dict() if self.hints else None,
            "locator_variants": {key: value.to_dict() for key, value in self.locator_variants.items()},
            "quality_metrics": self.quality_metrics,
            "last_seen": self.last_seen.isoformat(),
            "success_count": self.success_count,
            "fail_count": self.fail_count,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ElementMeta:
        last_seen_raw = payload.get("last_seen")
        last_seen = datetime.fromisoformat(last_seen_raw) if isinstance(last_seen_raw, str) else datetime.now(UTC)
        return cls(
            id=str(payload.get("id") or str(uuid.uuid4())),
            app_id=str(payload["app_id"]),
            page_name=str(payload["page_name"]),
            element_name=str(payload["element_name"]),
            field_type=str(payload["field_type"]),
            last_good_locator=LocatorSpec.from_dict(payload["last_good_locator"]) if payload.get("last_good_locator") else None,
            robust_locator=LocatorSpec.from_dict(payload["robust_locator"]) if payload.get("robust_locator") else None,
            strategy_id=payload.get("strategy_id"),
            signature=ElementSignature.from_dict(payload["signature"]) if payload.get("signature") else None,
            hints=HealingHints.from_dict(payload["hints"]) if payload.get("hints") else None,
            locator_variants={
                key: LocatorSpec.from_dict(value)
                for key, value in dict(payload.get("locator_variants") or {}).items()
                if isinstance(value, dict)
            },
            quality_metrics=dict(payload.get("quality_metrics") or {}),
            last_seen=last_seen,
            success_count=int(payload.get("success_count", 0)),
            fail_count=int(payload.get("fail_count", 0)),
        )


@dataclass(slots=True)
class StrategyTrace:
    stage: str
    strategy_id: str
    status: str
    candidate_count: int = 0
    selected_locator: LocatorSpec | None = None
    score: float | None = None
    validation: ValidationResult | None = None
    duration_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "strategy_id": self.strategy_id,
            "status": self.status,
            "candidate_count": self.candidate_count,
            "selected_locator": self.selected_locator.to_dict() if self.selected_locator else None,
            "score": self.score,
            "validation": self.validation.to_dict() if self.validation else None,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


@dataclass(slots=True)
class Recovered:
    status: str
    correlation_id: str
    locator_spec: LocatorSpec | None = None
    runtime_locator: Any = None
    metadata: ElementMeta | None = None
    strategy_id: str | None = None
    trace: list[StrategyTrace] = field(default_factory=list)
    error: str | None = None

    @property
    def playwright_locator(self) -> Any:
        if self.runtime_locator is None:
            return None
        return getattr(self.runtime_locator, "raw", self.runtime_locator)

    @property
    def raw_locator(self) -> Any:
        if self.runtime_locator is None:
            return None
        return getattr(self.runtime_locator, "raw", self.runtime_locator)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "correlation_id": self.correlation_id,
            "locator_spec": self.locator_spec.to_dict() if self.locator_spec else None,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "strategy_id": self.strategy_id,
            "trace": [entry.to_dict() for entry in self.trace],
            "error": self.error,
        }


@dataclass(slots=True)
class BuildInput:
    page: Any
    app_id: str
    page_name: str
    element_name: str
    field_type: str
    fallback: LocatorSpec
    vars: dict[str, str] = field(default_factory=dict)
    intent: Intent = field(default_factory=Intent)
    hints: HealingHints | None = None
    correlation_id: str = ""
    existing_meta: ElementMeta | None = None


@dataclass(slots=True)
class CandidateSpec:
    strategy_id: str
    locator: LocatorSpec
    stage: str
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IndexedElement:
    element_id: str
    element_name: str
    tag: str
    text: str = ""
    normalized_text: str = ""
    attr_id: str = ""
    attr_name: str = ""
    class_tokens: list[str] = field(default_factory=list)
    role: str = ""
    aria_label: str = ""
    placeholder: str = ""
    container_path: str = ""
    parent_signature: str = ""
    neighbor_text: str = ""
    position_signature: str = ""
    xpath: str = ""
    css: str = ""
    fingerprint_hash: str = ""
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "element_name": self.element_name,
            "tag": self.tag,
            "text": self.text,
            "normalized_text": self.normalized_text,
            "attr_id": self.attr_id,
            "attr_name": self.attr_name,
            "class_tokens": list(self.class_tokens),
            "role": self.role,
            "aria_label": self.aria_label,
            "placeholder": self.placeholder,
            "container_path": self.container_path,
            "parent_signature": self.parent_signature,
            "neighbor_text": self.neighbor_text,
            "position_signature": self.position_signature,
            "xpath": self.xpath,
            "css": self.css,
            "fingerprint_hash": self.fingerprint_hash,
            "metadata_json": dict(self.metadata_json or {}),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> IndexedElement:
        return cls(
            element_id=str(payload.get("element_id") or str(uuid.uuid4())),
            element_name=str(payload.get("element_name") or ""),
            tag=str(payload.get("tag") or ""),
            text=str(payload.get("text") or ""),
            normalized_text=str(payload.get("normalized_text") or ""),
            attr_id=str(payload.get("attr_id") or ""),
            attr_name=str(payload.get("attr_name") or ""),
            class_tokens=[str(token) for token in list(payload.get("class_tokens") or []) if str(token).strip()],
            role=str(payload.get("role") or ""),
            aria_label=str(payload.get("aria_label") or ""),
            placeholder=str(payload.get("placeholder") or ""),
            container_path=str(payload.get("container_path") or ""),
            parent_signature=str(payload.get("parent_signature") or ""),
            neighbor_text=str(payload.get("neighbor_text") or ""),
            position_signature=str(payload.get("position_signature") or ""),
            xpath=str(payload.get("xpath") or ""),
            css=str(payload.get("css") or ""),
            fingerprint_hash=str(payload.get("fingerprint_hash") or ""),
            metadata_json=dict(payload.get("metadata_json") or {}),
        )


@dataclass(slots=True)
class PageIndex:
    app_id: str
    page_name: str
    dom_hash: str
    snapshot_version: str = "v1"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    elements: list[IndexedElement] = field(default_factory=list)

    def key(self) -> tuple[str, str]:
        return (self.app_id, self.page_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "app_id": self.app_id,
            "page_name": self.page_name,
            "dom_hash": self.dom_hash,
            "snapshot_version": self.snapshot_version,
            "created_at": self.created_at.isoformat(),
            "elements": [item.to_dict() for item in self.elements],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PageIndex:
        created_at_raw = payload.get("created_at")
        created_at = datetime.fromisoformat(created_at_raw) if isinstance(created_at_raw, str) else datetime.now(UTC)
        elements_raw = list(payload.get("elements") or [])
        elements: list[IndexedElement] = []
        for item in elements_raw:
            if not isinstance(item, dict):
                continue
            try:
                elements.append(IndexedElement.from_dict(item))
            except Exception:
                continue
        return cls(
            id=str(payload.get("id") or str(uuid.uuid4())),
            app_id=str(payload.get("app_id") or ""),
            page_name=str(payload.get("page_name") or ""),
            dom_hash=str(payload.get("dom_hash") or ""),
            snapshot_version=str(payload.get("snapshot_version") or "v1"),
            created_at=created_at,
            elements=elements,
        )
