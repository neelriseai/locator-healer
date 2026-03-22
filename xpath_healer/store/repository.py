"""Repository abstraction for metadata and events."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from xpath_healer.core.models import ElementMeta, PageIndex


class MetadataRepository(ABC):
    @abstractmethod
    async def find(self, app_id: str, page_name: str, element_name: str) -> ElementMeta | None:
        raise NotImplementedError

    @abstractmethod
    async def upsert(self, meta: ElementMeta) -> None:
        raise NotImplementedError

    @abstractmethod
    async def find_candidates_by_page(
        self,
        app_id: str,
        page_name: str,
        field_type: str,
        limit: int = 25,
    ) -> list[ElementMeta]:
        raise NotImplementedError

    @abstractmethod
    async def get_page_index(self, app_id: str, page_name: str) -> PageIndex | None:
        raise NotImplementedError

    @abstractmethod
    async def upsert_page_index(self, page_index: PageIndex) -> None:
        raise NotImplementedError

    @abstractmethod
    async def log_event(self, event: dict[str, Any]) -> None:
        raise NotImplementedError
