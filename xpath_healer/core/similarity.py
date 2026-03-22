"""Signature similarity scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from xpath_healer.core.models import ElementSignature
from xpath_healer.utils.text import fuzzy_ratio, normalize_text


_DYNAMIC_TOKEN_RE = re.compile(r"(?:\d{4,}|[a-f0-9]{8,})")


@dataclass(slots=True)
class SimilarityScore:
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)


class SimilarityService:
    def __init__(self, threshold: float = 0.72) -> None:
        self.threshold = threshold
        self.attr_weight = 0.55
        self.text_weight = 0.20
        self.tag_weight = 0.15
        self.container_weight = 0.10

    def score(self, left: ElementSignature, right: ElementSignature) -> SimilarityScore:
        attr_score = self._attribute_score(left, right)
        text_score = fuzzy_ratio(left.short_text, right.short_text)
        tag_score = 1.0 if normalize_text(left.tag) == normalize_text(right.tag) else 0.0
        container_score = self._container_score(left.container_path, right.container_path)
        penalty = self._volatility_penalty(left, right)

        weighted = (
            self.attr_weight * attr_score
            + self.text_weight * text_score
            + self.tag_weight * tag_score
            + self.container_weight * container_score
            - penalty
        )
        total = min(max(weighted, 0.0), 1.0)
        return SimilarityScore(
            score=total,
            breakdown={
                "attrs": attr_score,
                "text": text_score,
                "tag": tag_score,
                "container": container_score,
                "penalty": penalty,
            },
        )

    def is_similar(self, similarity: SimilarityScore, threshold: float | None = None) -> bool:
        return similarity.score >= (threshold if threshold is not None else self.threshold)

    def _attribute_score(self, left: ElementSignature, right: ElementSignature) -> float:
        if not left.stable_attrs and not right.stable_attrs:
            return 0.0
        keys = set(left.stable_attrs) | set(right.stable_attrs)
        if not keys:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0
        for key in keys:
            weight = self._weight_for_attr(key)
            total_weight += weight
            lv = left.stable_attrs.get(key, "")
            rv = right.stable_attrs.get(key, "")
            if not lv and not rv:
                weighted_sum += weight
                continue
            weighted_sum += weight * fuzzy_ratio(lv, rv)

        return weighted_sum / total_weight if total_weight else 0.0

    @staticmethod
    def _weight_for_attr(attr: str) -> float:
        key = normalize_text(attr)
        if key in {"data-testid", "name", "formcontrolname"}:
            return 1.0
        if key in {"aria-label", "placeholder", "role", "col-id"}:
            return 0.9
        if key in {"href", "aria-colindex"}:
            return 0.6
        return 0.45

    @staticmethod
    def _container_score(left: list[str], right: list[str]) -> float:
        if not left and not right:
            return 0.0
        lset = set(normalize_text(x) for x in left if x)
        rset = set(normalize_text(x) for x in right if x)
        if not lset and not rset:
            return 0.0
        intersection = len(lset & rset)
        union = len(lset | rset)
        if union == 0:
            return 0.0
        return intersection / union

    def _volatility_penalty(self, left: ElementSignature, right: ElementSignature) -> float:
        penalty = 0.0
        for value in list(left.stable_attrs.values()) + list(right.stable_attrs.values()):
            if _DYNAMIC_TOKEN_RE.search(value or ""):
                penalty += 0.015
        return min(penalty, 0.15)

