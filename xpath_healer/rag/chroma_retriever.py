"""ChromaDB-backed retriever for RAG assist."""

from __future__ import annotations

import json
import os
from typing import Any

from xpath_healer.rag.retriever import Retriever

try:
    import chromadb  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    chromadb = None  # type: ignore[assignment]


class ChromaRetriever(Retriever):
    def __init__(
        self,
        chroma_path: str = "",
        rag_collection: str = "",
        elements_collection: str = "",
        app_id: str = "",
        page_name: str = "",
        field_type: str = "",
    ) -> None:
        self.chroma_path = (chroma_path or os.getenv("XH_CHROMA_PATH") or "artifacts/chroma").strip()
        self.rag_collection_name = (rag_collection or os.getenv("XH_CHROMA_RAG_COLLECTION") or "xh_rag_documents").strip()
        self.elements_collection_name = (
            elements_collection or os.getenv("XH_CHROMA_ELEMENTS_COLLECTION") or "xh_elements"
        ).strip()
        self.app_id = app_id
        self.page_name = page_name
        self.field_type = field_type
        self._client: Any = None
        self._rag_collection: Any = None
        self._elements_collection: Any = None

    def set_query_context(self, app_id: str, page_name: str, field_type: str = "") -> None:
        self.app_id = app_id or ""
        self.page_name = page_name or ""
        self.field_type = field_type or ""

    async def connect(self) -> None:
        if self._rag_collection is not None and self._elements_collection is not None:
            return
        if chromadb is None:
            raise RuntimeError("chromadb is not installed. Install with: python -m pip install chromadb")
        os.makedirs(self.chroma_path, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self.chroma_path)  # type: ignore[union-attr]
        self._rag_collection = self._client.get_or_create_collection(
            name=self.rag_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._elements_collection = self._client.get_or_create_collection(
            name=self.elements_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def close(self) -> None:
        self._client = None
        self._rag_collection = None
        self._elements_collection = None

    async def retrieve(self, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        if not query_embedding:
            return []
        await self.connect()
        limit = max(1, int(top_k))

        rag_rows = self._query_collection(
            collection=self._rag_collection,
            where=self._build_where(include_field_type=True),
            query_embedding=query_embedding,
            limit=limit,
        )
        if rag_rows:
            return [self._row_to_rag_doc(row) for row in rag_rows]

        element_rows = self._query_collection(
            collection=self._elements_collection,
            where=self._build_where(include_field_type=True),
            query_embedding=query_embedding,
            limit=limit,
        )
        return [self._row_to_element_candidate(row) for row in element_rows]

    def _build_where(self, include_field_type: bool) -> dict[str, Any] | None:
        filters: dict[str, str] = {}
        if self.app_id:
            filters["app_id"] = self.app_id
        if self.page_name:
            filters["page_name"] = self.page_name
        if include_field_type and self.field_type:
            filters["field_type"] = self.field_type
        if not filters:
            return None
        clauses = [{key: value} for key, value in filters.items()]
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def _query_collection(
        self,
        collection: Any,
        query_embedding: list[float],
        limit: int,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if collection is None:
            return []
        try:
            query_kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": max(1, int(limit)),
                "include": ["metadatas", "documents", "distances"],
            }
            if where:
                query_kwargs["where"] = where
            result = collection.query(**query_kwargs)
        except Exception:
            return []

        ids = (result or {}).get("ids") or [[]]
        metadatas = (result or {}).get("metadatas") or [[]]
        documents = (result or {}).get("documents") or [[]]
        distances = (result or {}).get("distances") or [[]]
        row_ids = ids[0] if ids else []
        row_metadatas = metadatas[0] if metadatas else []
        row_documents = documents[0] if documents else []
        row_distances = distances[0] if distances else []

        out: list[dict[str, Any]] = []
        for idx, item_id in enumerate(row_ids):
            distance = float(row_distances[idx]) if idx < len(row_distances) and row_distances[idx] is not None else 1.0
            similarity = max(0.0, 1.0 - distance)
            out.append(
                {
                    "id": item_id,
                    "metadata": row_metadatas[idx] if idx < len(row_metadatas) else {},
                    "document": row_documents[idx] if idx < len(row_documents) else "",
                    "similarity": similarity,
                }
            )
        return out

    @staticmethod
    def _decode_json(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None
        return None

    def _row_to_rag_doc(self, row: dict[str, Any]) -> dict[str, Any]:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        payload_metadata = self._decode_json(metadata.get("metadata_json")) or {}
        locator = payload_metadata.get("locator") if isinstance(payload_metadata, dict) else None
        out = {
            "app_id": metadata.get("app_id"),
            "page_name": metadata.get("page_name"),
            "element_name": metadata.get("element_name"),
            "source": metadata.get("source"),
            "chunk_text": row.get("document"),
            "metadata": payload_metadata,
            "similarity": float(row.get("similarity") or 0.0),
        }
        if isinstance(locator, dict):
            out["locator"] = locator
        return out

    def _row_to_element_candidate(self, row: dict[str, Any]) -> dict[str, Any]:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        return {
            "app_id": metadata.get("app_id"),
            "page_name": metadata.get("page_name"),
            "element_name": metadata.get("element_name"),
            "field_type": metadata.get("field_type"),
            "last_good_locator": self._decode_json(metadata.get("last_good_locator_json")),
            "robust_locator": self._decode_json(metadata.get("robust_locator_json")),
            "signature": self._decode_json(metadata.get("signature_json")),
            "quality_metrics": self._decode_json(metadata.get("quality_metrics_json")) or {},
            "similarity": float(row.get("similarity") or 0.0),
        }
