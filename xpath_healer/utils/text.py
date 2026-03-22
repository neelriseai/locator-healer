"""Text normalization and lightweight matching helpers."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable


_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    """Normalize text for stable comparisons."""
    if value is None:
        return ""
    return _SPACE_RE.sub(" ", value).strip().casefold()


def tokenize(value: str | None) -> list[str]:
    normalized = normalize_text(value)
    if not normalized:
        return []
    return [token for token in normalized.split(" ") if token]


def token_subset_match(expected: str | None, actual: str | None) -> bool:
    expected_tokens = set(tokenize(expected))
    actual_tokens = set(tokenize(actual))
    if not expected_tokens:
        return False
    return expected_tokens.issubset(actual_tokens)


def contains_match(expected: str | None, actual: str | None) -> bool:
    normalized_expected = normalize_text(expected)
    normalized_actual = normalize_text(actual)
    if not normalized_expected:
        return False
    return normalized_expected in normalized_actual


def exact_match(expected: str | None, actual: str | None) -> bool:
    return normalize_text(expected) == normalize_text(actual)


def safe_join(tokens: Iterable[str], sep: str = " ") -> str:
    return sep.join(token for token in tokens if token)


def fuzzy_ratio(left: str | None, right: str | None) -> float:
    """Return similarity ratio in [0, 1] with rapidfuzz fallback."""
    left_n = normalize_text(left)
    right_n = normalize_text(right)
    if not left_n and not right_n:
        return 1.0
    if not left_n or not right_n:
        return 0.0

    try:
        from rapidfuzz.fuzz import ratio as rf_ratio  # type: ignore

        return float(rf_ratio(left_n, right_n)) / 100.0
    except Exception:
        return SequenceMatcher(None, left_n, right_n).ratio()


def coerce_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default

