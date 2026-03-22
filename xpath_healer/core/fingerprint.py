"""DOM fingerprint building and lightweight weighted matching."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from xpath_healer.core.models import ElementSignature, Intent
from xpath_healer.utils.text import fuzzy_ratio, normalize_text, safe_join


DEFAULT_FINGERPRINT_WEIGHTS: dict[str, float] = {
    "tag": 0.20,
    "type": 0.12,
    "role": 0.12,
    "label": 0.16,
    "text": 0.14,
    "container": 0.16,
    "field_type": 0.10,
}


@dataclass(slots=True)
class Fingerprint:
    text: str
    hash_value: str
    tokens: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class FingerprintMatch:
    score: float
    exact_hash: bool
    breakdown: dict[str, float] = field(default_factory=dict)


class FingerprintService:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = dict(weights or DEFAULT_FINGERPRINT_WEIGHTS)

    def build(
        self,
        signature: ElementSignature | None,
        *,
        field_type: str = "",
        intent: Intent | None = None,
        element_name: str = "",
    ) -> Fingerprint:
        tokens: dict[str, str] = {}
        if signature is not None:
            tag = normalize_text(signature.tag)
            if tag:
                tokens["tag"] = tag

            stable_attrs = signature.stable_attrs or {}
            for key in ("type", "role", "data-testid", "name", "formcontrolname", "placeholder", "col-id"):
                value = normalize_text(stable_attrs.get(key))
                if value:
                    tokens[key] = value

            short_text = normalize_text(signature.short_text)
            if short_text:
                tokens["text"] = short_text[:80]

            container_tokens = [normalize_text(item) for item in list(signature.container_path or [])[:3]]
            container_tokens = [item for item in container_tokens if item]
            if container_tokens:
                tokens["container"] = safe_join(container_tokens, sep=">")

        label_token = ""
        if intent is not None:
            label_token = normalize_text(intent.label or intent.text)
        if not label_token:
            label_token = normalize_text(element_name.replace("_", " "))
        if label_token:
            tokens["label"] = label_token[:80]

        field_type_norm = normalize_text(field_type)
        if field_type_norm:
            tokens["field_type"] = field_type_norm

        canonical_pairs = [f"{key}={tokens[key]}" for key in sorted(tokens) if tokens.get(key)]
        text = safe_join(canonical_pairs, sep="|")
        hash_value = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
        return Fingerprint(text=text, hash_value=hash_value, tokens=tokens)

    def compare(self, expected: Fingerprint, candidate: Fingerprint) -> FingerprintMatch:
        if expected.hash_value and expected.hash_value == candidate.hash_value:
            return FingerprintMatch(score=0.98, exact_hash=True, breakdown={"exact_hash": 1.0})

        breakdown: dict[str, float] = {}
        weighted_total = 0.0
        weighted_match = 0.0

        for key, expected_value in expected.tokens.items():
            if not expected_value:
                continue
            weight = float(self.weights.get(key, 0.05))
            weighted_total += weight
            candidate_value = candidate.tokens.get(key, "")
            if not candidate_value:
                breakdown[key] = 0.0
                continue
            similarity = self._token_similarity(key, expected_value, candidate_value)
            weighted_match += weight * similarity
            breakdown[key] = round(similarity, 6)

        score = (weighted_match / weighted_total) if weighted_total > 0 else 0.0
        return FingerprintMatch(score=min(max(score, 0.0), 1.0), exact_hash=False, breakdown=breakdown)

    def _token_similarity(self, key: str, expected_value: str, candidate_value: str) -> float:
        if expected_value == candidate_value:
            return 1.0

        if key in {"text", "label"}:
            return fuzzy_ratio(expected_value, candidate_value)

        if key == "container":
            return self._container_similarity(expected_value, candidate_value)

        return 0.0

    @staticmethod
    def _container_similarity(left: str, right: str) -> float:
        left_tokens = {token for token in left.split(">") if token}
        right_tokens = {token for token in right.split(">") if token}
        if not left_tokens and not right_tokens:
            return 1.0
        if not left_tokens or not right_tokens:
            return 0.0
        union = left_tokens | right_tokens
        if not union:
            return 0.0
        return len(left_tokens & right_tokens) / len(union)

    @staticmethod
    def confidence_band(score: float) -> str:
        if score >= 0.90:
            return "high"
        if score >= 0.75:
            return "medium"
        return "low"

    @staticmethod
    def to_dict(fp: Fingerprint) -> dict[str, Any]:
        return {"text": fp.text, "hash": fp.hash_value, "tokens": dict(fp.tokens)}
