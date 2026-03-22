"""Composite metadata repository (DB primary, JSON fallback, dual write)."""

from __future__ import annotations

import asyncio
from typing import Any

from xpath_healer.core.models import ElementMeta, PageIndex
from xpath_healer.store.repository import MetadataRepository


class DualMetadataRepository(MetadataRepository):
    def __init__(self, primary: MetadataRepository, fallback: MetadataRepository) -> None:
        self.primary = primary
        self.fallback = fallback
        self.events: list[dict[str, Any]] = []
        primary_events = getattr(primary, "events", None)
        if isinstance(primary_events, list):
            self.events = primary_events
        else:
            fallback_events = getattr(fallback, "events", None)
            if isinstance(fallback_events, list):
                self.events = fallback_events

    async def find(self, app_id: str, page_name: str, element_name: str) -> ElementMeta | None:
        primary_error: Exception | None = None
        try:
            primary_result = await self.primary.find(app_id, page_name, element_name)
            if primary_result is not None:
                return primary_result
        except Exception as exc:
            primary_error = exc

        fallback_result = await self.fallback.find(app_id, page_name, element_name)
        if fallback_result is not None:
            try:
                await self.primary.upsert(fallback_result)
            except Exception:
                # Best-effort warm-up into primary store.
                pass
            return fallback_result

        if primary_error is not None:
            raise primary_error
        return None

    async def upsert(self, meta: ElementMeta) -> None:
        primary_error: Exception | None = None
        fallback_error: Exception | None = None

        try:
            await self.primary.upsert(meta)
        except Exception as exc:
            primary_error = exc

        try:
            await self.fallback.upsert(meta)
        except Exception as exc:
            fallback_error = exc

        if primary_error is None or fallback_error is None:
            return
        raise RuntimeError(f"Dual upsert failed: primary={primary_error}; fallback={fallback_error}")

    async def find_candidates_by_page(
        self,
        app_id: str,
        page_name: str,
        field_type: str,
        limit: int = 25,
    ) -> list[ElementMeta]:
        primary_error: Exception | None = None
        try:
            primary_results = await self.primary.find_candidates_by_page(app_id, page_name, field_type, limit=limit)
            if primary_results:
                return primary_results
        except Exception as exc:
            primary_error = exc

        fallback_results = await self.fallback.find_candidates_by_page(app_id, page_name, field_type, limit=limit)
        if fallback_results:
            for meta in fallback_results:
                try:
                    await self.primary.upsert(meta)
                except Exception:
                    break
            return fallback_results

        if primary_error is not None:
            raise primary_error
        return []

    async def get_page_index(self, app_id: str, page_name: str) -> PageIndex | None:
        primary_error: Exception | None = None
        try:
            primary_result = await self.primary.get_page_index(app_id, page_name)
            if primary_result is not None:
                return primary_result
        except Exception as exc:
            primary_error = exc

        fallback_result = await self.fallback.get_page_index(app_id, page_name)
        if fallback_result is not None:
            try:
                await self.primary.upsert_page_index(fallback_result)
            except Exception:
                pass
            return fallback_result

        if primary_error is not None:
            raise primary_error
        return None

    async def upsert_page_index(self, page_index: PageIndex) -> None:
        primary_error: Exception | None = None
        fallback_error: Exception | None = None

        try:
            await self.primary.upsert_page_index(page_index)
        except Exception as exc:
            primary_error = exc

        try:
            await self.fallback.upsert_page_index(page_index)
        except Exception as exc:
            fallback_error = exc

        if primary_error is None or fallback_error is None:
            return
        raise RuntimeError(f"Dual upsert_page_index failed: primary={primary_error}; fallback={fallback_error}")

    async def log_event(self, event: dict[str, Any]) -> None:
        primary_error: Exception | None = None
        fallback_error: Exception | None = None

        try:
            await self.primary.log_event(event)
        except Exception as exc:
            primary_error = exc

        try:
            await self.fallback.log_event(event)
        except Exception as exc:
            fallback_error = exc

        if primary_error is None or fallback_error is None:
            return
        raise RuntimeError(f"Dual log_event failed: primary={primary_error}; fallback={fallback_error}")

    async def close(self) -> None:
        await self._close_backend(self.primary)
        await self._close_backend(self.fallback)

    async def _close_backend(self, backend: MetadataRepository) -> None:
        close_method = getattr(backend, "close", None)
        if close_method is None:
            return
        maybe = close_method()
        if asyncio.iscoroutine(maybe):
            await maybe
