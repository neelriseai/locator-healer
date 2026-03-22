"""Playwright DOM snapshotter with small TTL cache."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from xpath_healer.core.automation import AutomationAdapter


@dataclass(slots=True)
class SnapshotRecord:
    html: str
    captured_at: float


class DomSnapshotter:
    def __init__(self, adapter: AutomationAdapter, cache_ttl_sec: int = 30) -> None:
        self.adapter = adapter
        self.cache_ttl_sec = cache_ttl_sec
        self._cache: dict[tuple[int, str], SnapshotRecord] = {}

    async def capture(self, page: Any, scoped_locator: Any | None = None, use_cache: bool = True) -> str:
        cache_key = self._cache_key(page, scoped_locator=scoped_locator)
        now = time.time()
        cached = self._cache.get(cache_key)
        if use_cache and cached and (now - cached.captured_at) <= self.cache_ttl_sec:
            return cached.html

        if scoped_locator is not None:
            html = await scoped_locator.evaluate("el => el.outerHTML")
        else:
            html = await self.adapter.capture_page_html(page)

        html = html or ""
        self._cache[cache_key] = SnapshotRecord(html=html, captured_at=now)
        return html

    @staticmethod
    def _cache_key(page: Any, scoped_locator: Any | None = None) -> tuple[int, str]:
        target = scoped_locator or page
        page_token = ""
        if scoped_locator is None:
            page_token = DomSnapshotter._page_token(page)
        return (id(target), page_token)

    @staticmethod
    def _page_token(page: Any) -> str:
        for attr_name in ("current_url", "url"):
            try:
                value = getattr(page, attr_name, "")
            except Exception:
                continue
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            token = str(value or "").strip()
            if token:
                return token
        return ""
