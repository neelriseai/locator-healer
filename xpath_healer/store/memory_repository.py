"""In-memory metadata repository for standalone core testing."""

from __future__ import annotations

from typing import Any

from xpath_healer.core.models import ElementMeta, PageIndex
from xpath_healer.store.repository import MetadataRepository


class InMemoryMetadataRepository(MetadataRepository):
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str], ElementMeta] = {}
        self._page_indexes: dict[tuple[str, str], PageIndex] = {}
        self.events: list[dict[str, Any]] = []

    async def find(self, app_id: str, page_name: str, element_name: str) -> ElementMeta | None:
        return self._items.get((app_id, page_name, element_name))

    async def upsert(self, meta: ElementMeta) -> None:
        self._items[meta.key()] = meta

    async def find_candidates_by_page(
        self,
        app_id: str,
        page_name: str,
        field_type: str,
        limit: int = 25,
    ) -> list[ElementMeta]:
        matches: list[ElementMeta] = []
        for meta in self._items.values():
            if meta.app_id != app_id:
                continue
            if meta.page_name != page_name:
                continue
            if field_type and meta.field_type != field_type:
                continue
            matches.append(meta)
            if len(matches) >= limit:
                break
        return matches

    async def get_page_index(self, app_id: str, page_name: str) -> PageIndex | None:
        return self._page_indexes.get((app_id, page_name))

    async def upsert_page_index(self, page_index: PageIndex) -> None:
        self._page_indexes[page_index.key()] = page_index

    async def log_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)
