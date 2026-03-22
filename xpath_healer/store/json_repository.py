"""File-backed JSON metadata repository with page-wise storage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from xpath_healer.core.models import ElementMeta, PageIndex
from xpath_healer.store.repository import MetadataRepository


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", (value or "").strip())
    return cleaned or "default"


class JsonMetadataRepository(MetadataRepository):
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.root_dir / "events.jsonl"
        self.events: list[dict[str, Any]] = []

    async def find(self, app_id: str, page_name: str, element_name: str) -> ElementMeta | None:
        payload = self._read_page_file(app_id, page_name)
        item = (payload.get("elements") or {}).get(element_name)
        if not item:
            return None
        try:
            return ElementMeta.from_dict(item)
        except Exception:
            return None

    async def upsert(self, meta: ElementMeta) -> None:
        payload = self._read_page_file(meta.app_id, meta.page_name)
        elements = payload.setdefault("elements", {})
        elements[meta.element_name] = meta.to_dict()
        payload["app_id"] = meta.app_id
        payload["page_name"] = meta.page_name
        self._write_page_file(meta.app_id, meta.page_name, payload)

    async def find_candidates_by_page(
        self,
        app_id: str,
        page_name: str,
        field_type: str,
        limit: int = 25,
    ) -> list[ElementMeta]:
        payload = self._read_page_file(app_id, page_name)
        elements = (payload.get("elements") or {}).values()
        out: list[ElementMeta] = []
        for raw in elements:
            try:
                meta = ElementMeta.from_dict(raw)
            except Exception:
                continue
            if field_type and meta.field_type != field_type:
                continue
            out.append(meta)
            if len(out) >= limit:
                break
        return out

    async def get_page_index(self, app_id: str, page_name: str) -> PageIndex | None:
        payload = self._read_page_file(app_id, page_name)
        raw = payload.get("page_index")
        if not isinstance(raw, dict):
            return None
        try:
            return PageIndex.from_dict(raw)
        except Exception:
            return None

    async def upsert_page_index(self, page_index: PageIndex) -> None:
        payload = self._read_page_file(page_index.app_id, page_index.page_name)
        payload["page_index"] = page_index.to_dict()
        self._write_page_file(page_index.app_id, page_index.page_name, payload)

    async def log_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        with self.events_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str))
            fh.write("\n")

    def _page_file(self, app_id: str, page_name: str) -> Path:
        app_dir = self.root_dir / _safe_name(app_id)
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / f"{_safe_name(page_name)}.json"

    def _read_page_file(self, app_id: str, page_name: str) -> dict[str, Any]:
        path = self._page_file(app_id, page_name)
        if not path.exists():
            return {"app_id": app_id, "page_name": page_name, "elements": {}, "page_index": None}
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                return {"app_id": app_id, "page_name": page_name, "elements": {}}
            raw.setdefault("app_id", app_id)
            raw.setdefault("page_name", page_name)
            raw.setdefault("elements", {})
            raw.setdefault("page_index", None)
            return raw
        except Exception:
            return {"app_id": app_id, "page_name": page_name, "elements": {}, "page_index": None}

    def _write_page_file(self, app_id: str, page_name: str, payload: dict[str, Any]) -> None:
        path = self._page_file(app_id, page_name)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=True)
        tmp.replace(path)
