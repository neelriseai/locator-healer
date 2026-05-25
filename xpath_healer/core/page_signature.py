"""Cheap, stable page-signature hash used by the workflow replay cache.

Goal: distinguish "same UI shape" from "UI has materially changed"
without persisting the raw DOM. Hashing structural tokens (tag chain +
stable attributes) keeps the signature noise-resistant — minor text
edits and dynamic IDs don't change it; an A/B test that swaps the form
layout does.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

# Attributes that change rarely and disambiguate elements/regions.
_STABLE_ATTR_TOKENS = (
    "data-testid",
    "id",
    "name",
    "role",
    "aria-label",
    "type",
    "for",
)

_TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9:-]*)([^>]*)>")
_ATTR_RE = re.compile(r'([a-zA-Z_:][\w:.-]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')

# Cap on tokens we hash. Past this the marginal disambiguation falls
# off and prompt/storage costs grow.
_MAX_TOKENS = 800


def compute_page_signature_hash(html: str | None) -> str:
    """Return a 16-char hex prefix of a sha256 over stable structure.

    Empty / None input → empty string. Caller treats empty as "no
    signature available" and falls back to outcome-only trust.
    """
    if not html:
        return ""
    tokens = list(_iter_tokens(html))
    if not tokens:
        return ""
    payload = "\n".join(tokens[:_MAX_TOKENS])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _iter_tokens(html: str) -> Iterable[str]:
    for match in _TAG_RE.finditer(html):
        tag = (match.group(1) or "").lower()
        if tag in {"script", "style", "svg", "path", "g", "br", "meta", "link"}:
            continue
        attrs_blob = match.group(2) or ""
        attr_pairs: list[str] = []
        for attr_match in _ATTR_RE.finditer(attrs_blob):
            name = (attr_match.group(1) or "").lower()
            if name not in _STABLE_ATTR_TOKENS:
                continue
            value = (attr_match.group(2) or attr_match.group(3) or "").strip().lower()
            if not value:
                continue
            attr_pairs.append(f"{name}={value}")
        if attr_pairs:
            yield f"{tag}[" + ",".join(sorted(attr_pairs)) + "]"
        else:
            yield tag
