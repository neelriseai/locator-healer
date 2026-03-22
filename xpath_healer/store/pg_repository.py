"""PostgreSQL repository implementation for metadata and healing events."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from xpath_healer.core.models import ElementMeta, IndexedElement, PageIndex
from xpath_healer.store.repository import MetadataRepository

try:
    import asyncpg  # type: ignore
except Exception:  # pragma: no cover - dependency may be optional at runtime
    asyncpg = None  # type: ignore[assignment]

try:
    import chromadb  # type: ignore
except Exception:  # pragma: no cover - dependency may be optional at runtime
    chromadb = None  # type: ignore[assignment]


LOGGER = logging.getLogger("xpath_healer.store.pg_repository")


class PostgresMetadataRepository(MetadataRepository):
    def __init__(
        self,
        dsn: str,
        pool_min_size: int = 1,
        pool_max_size: int = 10,
        auto_init_schema: bool = False,
    ) -> None:
        self.dsn = dsn
        self.pool_min_size = max(1, int(pool_min_size))
        self.pool_max_size = max(self.pool_min_size, int(pool_max_size))
        self.auto_init_schema = bool(auto_init_schema)
        self._pool: Any = None
        self._embedder: Any = None
        self._embedder_resolved = False
        self._embedding_dim = self._safe_env_int("XH_OPENAI_EMBED_DIM", default=1536, minimum=8)
        self._embedding_writes_enabled = self._safe_env_bool("XH_EMBEDDING_WRITE_ENABLED", default=True)
        self._rag_doc_max_chars = self._safe_env_int("XH_RAG_DOC_MAX_CHARS", default=1400, minimum=300)
        self._chroma_path = (os.getenv("XH_CHROMA_PATH") or "artifacts/chroma").strip()
        self._chroma_rag_collection_name = (os.getenv("XH_CHROMA_RAG_COLLECTION") or "xh_rag_documents").strip()
        self._chroma_elements_collection_name = (os.getenv("XH_CHROMA_ELEMENTS_COLLECTION") or "xh_elements").strip()
        self._chroma_client: Any = None
        self._chroma_rag_collection: Any = None
        self._chroma_elements_collection: Any = None
        self._chroma_unavailable_logged = False

    async def connect(self) -> None:
        if self._pool is not None:
            return
        if asyncpg is None:
            raise RuntimeError("asyncpg is not installed. Install with: python -m pip install asyncpg")
        self._pool = await asyncpg.create_pool(  # type: ignore[union-attr]
            dsn=self.dsn,
            min_size=self.pool_min_size,
            max_size=self.pool_max_size,
            command_timeout=30,
        )
        self._ensure_chroma_collections()
        if self.auto_init_schema:
            await self.init_schema()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        self._chroma_client = None
        self._chroma_rag_collection = None
        self._chroma_elements_collection = None

    async def init_schema(self) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(self.schema_sql())

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            await self.connect()
        return self._pool

    async def find(self, app_id: str, page_name: str, element_name: str) -> ElementMeta | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                  id,
                  app_id,
                  page_name,
                  element_name,
                  field_type,
                  last_good_locator,
                  robust_locator,
                  strategy_id,
                  signature,
                  hints,
                  locator_variants,
                  quality_metrics,
                  last_seen,
                  success_count,
                  fail_count
                FROM elements
                WHERE app_id=$1 AND page_name=$2 AND element_name=$3
                LIMIT 1
                """,
                app_id,
                page_name,
                element_name,
            )
            if not row:
                return None

            payload = self._row_to_payload(row)
            if not payload.get("locator_variants"):
                payload["locator_variants"] = await self._load_locator_variants(conn, str(row["id"]))
            if not payload.get("quality_metrics"):
                payload["quality_metrics"] = await self._load_quality_metrics(conn, str(row["id"]))
            return ElementMeta.from_dict(payload)

    async def upsert(self, meta: ElementMeta) -> None:
        pool = await self._ensure_pool()
        element_id = str(meta.id or uuid.uuid4())
        now_value = meta.last_seen if isinstance(meta.last_seen, datetime) else datetime.now(UTC)
        payload = meta.to_dict()
        rag_chunk_text = self._build_embedding_text(meta)
        embedding = await self._embed_text(rag_chunk_text)

        async with pool.acquire() as conn:
            stored_id = await conn.fetchval(
                """
                INSERT INTO elements (
                  id,
                  app_id,
                  page_name,
                  element_name,
                  field_type,
                  last_good_locator,
                  robust_locator,
                  strategy_id,
                  signature,
                  hints,
                  locator_variants,
                  quality_metrics,
                  last_seen,
                  success_count,
                  fail_count
                )
                VALUES (
                  $1::uuid,
                  $2,
                  $3,
                  $4,
                  $5,
                  $6::jsonb,
                  $7::jsonb,
                  $8,
                  $9::jsonb,
                  $10::jsonb,
                  $11::jsonb,
                  $12::jsonb,
                  $13::timestamptz,
                  $14,
                  $15
                )
                ON CONFLICT (app_id, page_name, element_name)
                DO UPDATE SET
                  field_type = EXCLUDED.field_type,
                  last_good_locator = EXCLUDED.last_good_locator,
                  robust_locator = EXCLUDED.robust_locator,
                  strategy_id = EXCLUDED.strategy_id,
                  signature = EXCLUDED.signature,
                  hints = EXCLUDED.hints,
                  locator_variants = EXCLUDED.locator_variants,
                  quality_metrics = EXCLUDED.quality_metrics,
                  last_seen = EXCLUDED.last_seen,
                  success_count = EXCLUDED.success_count,
                  fail_count = EXCLUDED.fail_count
                RETURNING id
                """,
                element_id,
                meta.app_id,
                meta.page_name,
                meta.element_name,
                meta.field_type,
                self._json_or_none(payload.get("last_good_locator")),
                self._json_or_none(payload.get("robust_locator")),
                meta.strategy_id,
                self._json_or_none(payload.get("signature")),
                self._json_or_none(payload.get("hints")),
                self._json_or_empty(payload.get("locator_variants")),
                self._json_or_empty(payload.get("quality_metrics")),
                now_value,
                int(meta.success_count),
                int(meta.fail_count),
            )
            element_uuid = str(stored_id)
            await self._sync_locator_variants(conn, element_uuid, payload.get("locator_variants") or {})
            await self._sync_quality_metrics(conn, element_uuid, payload.get("quality_metrics") or {})
            await self._upsert_element_rag_document(conn, meta, rag_chunk_text, embedding)

    async def find_candidates_by_page(
        self,
        app_id: str,
        page_name: str,
        field_type: str,
        limit: int = 25,
    ) -> list[ElementMeta]:
        pool = await self._ensure_pool()
        limit = max(1, int(limit))
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                  id,
                  app_id,
                  page_name,
                  element_name,
                  field_type,
                  last_good_locator,
                  robust_locator,
                  strategy_id,
                  signature,
                  hints,
                  locator_variants,
                  quality_metrics,
                  last_seen,
                  success_count,
                  fail_count
                FROM elements
                WHERE app_id=$1
                  AND page_name=$2
                  AND ($3 = '' OR field_type=$3)
                ORDER BY success_count DESC, last_seen DESC
                LIMIT $4
                """,
                app_id,
                page_name,
                field_type or "",
                limit,
            )

            out: list[ElementMeta] = []
            for row in rows:
                payload = self._row_to_payload(row)
                if not payload.get("locator_variants"):
                    payload["locator_variants"] = await self._load_locator_variants(conn, str(row["id"]))
                if not payload.get("quality_metrics"):
                    payload["quality_metrics"] = await self._load_quality_metrics(conn, str(row["id"]))
                out.append(ElementMeta.from_dict(payload))
            return out

    async def get_page_index(self, app_id: str, page_name: str) -> PageIndex | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                  page_id,
                  app_id,
                  page_name,
                  dom_hash,
                  snapshot_version,
                  created_at
                FROM page_index
                WHERE app_id=$1 AND page_name=$2
                ORDER BY created_at DESC
                LIMIT 1
                """,
                app_id,
                page_name,
            )
            if not row:
                return None

            page_id = str(row["page_id"])
            item_rows = await conn.fetch(
                """
                SELECT
                  element_id,
                  element_name,
                  tag,
                  text,
                  normalized_text,
                  attr_id,
                  attr_name,
                  class_tokens,
                  role,
                  aria_label,
                  placeholder,
                  container_path,
                  parent_signature,
                  neighbor_text,
                  position_signature,
                  xpath,
                  css,
                  fingerprint_hash,
                  metadata_json
                FROM indexed_elements
                WHERE page_id=$1::uuid
                ORDER BY ordinal ASC, id ASC
                """,
                page_id,
            )
            elements: list[IndexedElement] = []
            for item in item_rows:
                payload = {
                    "element_id": str(item.get("element_id") or ""),
                    "element_name": str(item.get("element_name") or ""),
                    "tag": str(item.get("tag") or ""),
                    "text": str(item.get("text") or ""),
                    "normalized_text": str(item.get("normalized_text") or ""),
                    "attr_id": str(item.get("attr_id") or ""),
                    "attr_name": str(item.get("attr_name") or ""),
                    "class_tokens": self._decode_json(item.get("class_tokens")) or [],
                    "role": str(item.get("role") or ""),
                    "aria_label": str(item.get("aria_label") or ""),
                    "placeholder": str(item.get("placeholder") or ""),
                    "container_path": str(item.get("container_path") or ""),
                    "parent_signature": str(item.get("parent_signature") or ""),
                    "neighbor_text": str(item.get("neighbor_text") or ""),
                    "position_signature": str(item.get("position_signature") or ""),
                    "xpath": str(item.get("xpath") or ""),
                    "css": str(item.get("css") or ""),
                    "fingerprint_hash": str(item.get("fingerprint_hash") or ""),
                    "metadata_json": self._decode_json(item.get("metadata_json")) or {},
                }
                elements.append(IndexedElement.from_dict(payload))

            created_at = row.get("created_at")
            created_at_value = created_at if isinstance(created_at, datetime) else datetime.now(UTC)
            return PageIndex(
                id=page_id,
                app_id=str(row.get("app_id") or ""),
                page_name=str(row.get("page_name") or ""),
                dom_hash=str(row.get("dom_hash") or ""),
                snapshot_version=str(row.get("snapshot_version") or "v1"),
                created_at=created_at_value,
                elements=elements,
            )

    async def upsert_page_index(self, page_index: PageIndex) -> None:
        pool = await self._ensure_pool()
        page_id = str(page_index.id or uuid.uuid4())
        created_at = page_index.created_at if isinstance(page_index.created_at, datetime) else datetime.now(UTC)
        async with pool.acquire() as conn:
            stored_page_id = await conn.fetchval(
                """
                INSERT INTO page_index (
                  page_id,
                  app_id,
                  page_name,
                  dom_hash,
                  snapshot_version,
                  created_at
                )
                VALUES ($1::uuid,$2,$3,$4,$5,$6::timestamptz)
                ON CONFLICT (app_id, page_name)
                DO UPDATE SET
                  dom_hash = EXCLUDED.dom_hash,
                  snapshot_version = EXCLUDED.snapshot_version,
                  created_at = EXCLUDED.created_at
                RETURNING page_id
                """,
                page_id,
                page_index.app_id,
                page_index.page_name,
                page_index.dom_hash,
                page_index.snapshot_version,
                created_at,
            )
            page_uuid = str(stored_page_id)
            await conn.execute("DELETE FROM indexed_elements WHERE page_id=$1::uuid", page_uuid)
            for ordinal, element in enumerate(page_index.elements):
                payload = element.to_dict()
                await conn.execute(
                    """
                    INSERT INTO indexed_elements (
                      page_id,
                      ordinal,
                      element_id,
                      element_name,
                      tag,
                      text,
                      normalized_text,
                      attr_id,
                      attr_name,
                      class_tokens,
                      role,
                      aria_label,
                      placeholder,
                      container_path,
                      parent_signature,
                      neighbor_text,
                      position_signature,
                      xpath,
                      css,
                      fingerprint_hash,
                      metadata_json
                    )
                    VALUES (
                      $1::uuid,
                      $2,
                      $3,
                      $4,
                      $5,
                      $6,
                      $7,
                      $8,
                      $9,
                      $10::jsonb,
                      $11,
                      $12,
                      $13,
                      $14,
                      $15,
                      $16,
                      $17,
                      $18,
                      $19,
                      $20,
                      $21::jsonb
                    )
                    """,
                    page_uuid,
                    int(ordinal),
                    payload.get("element_id"),
                    payload.get("element_name"),
                    payload.get("tag"),
                    payload.get("text"),
                    payload.get("normalized_text"),
                    payload.get("attr_id"),
                    payload.get("attr_name"),
                    self._json_or_empty(payload.get("class_tokens") or []),
                    payload.get("role"),
                    payload.get("aria_label"),
                    payload.get("placeholder"),
                    payload.get("container_path"),
                    payload.get("parent_signature"),
                    payload.get("neighbor_text"),
                    payload.get("position_signature"),
                    payload.get("xpath"),
                    payload.get("css"),
                    payload.get("fingerprint_hash"),
                    self._json_or_empty(payload.get("metadata_json") or {}),
                )

    async def log_event(self, event: dict[str, Any]) -> None:
        pool = await self._ensure_pool()
        event_payload = dict(event or {})
        element_uuid_text = self._safe_uuid_text(event_payload.get("element_id"))
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO events (
                  correlation_id,
                  app_id,
                  page_name,
                  element_name,
                  field_type,
                  stage,
                  status,
                  score,
                  details
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
                """,
                str(event_payload.get("correlation_id") or ""),
                event_payload.get("app_id"),
                event_payload.get("page_name"),
                event_payload.get("element_name"),
                event_payload.get("field_type"),
                event_payload.get("stage"),
                event_payload.get("status"),
                event_payload.get("score"),
                self._json_or_empty(event_payload.get("details") or {}),
            )
            await conn.execute(
                """
                INSERT INTO healing_events (
                  run_id,
                  element_id,
                  app_id,
                  page_name,
                  element_name,
                  stage,
                  failure_type,
                  final_locator,
                  outcome,
                  details
                )
                VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8::jsonb,$9,$10::jsonb)
                """,
                str(event_payload.get("run_id") or event_payload.get("correlation_id") or ""),
                element_uuid_text,
                event_payload.get("app_id"),
                event_payload.get("page_name"),
                event_payload.get("element_name"),
                event_payload.get("stage"),
                event_payload.get("failure_type"),
                self._json_or_none(event_payload.get("final_locator")),
                event_payload.get("status"),
                self._json_or_empty(event_payload.get("details") or {}),
            )

    async def search_rag_documents(
        self,
        query_embedding: list[float],
        app_id: str,
        page_name: str = "",
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        top_n = max(1, int(limit))
        if not query_embedding:
            return []
        rag_collection = self._get_chroma_rag_collection()
        if rag_collection is None:
            return []
        filters = self._chroma_where(
            {
                "app_id": app_id or "",
                "page_name": page_name or "",
            }
        )
        rows = self._query_chroma_collection(
            collection=rag_collection,
            query_embedding=query_embedding,
            limit=top_n,
            where=filters,
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            raw_metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            payload_metadata = self._decode_json(raw_metadata.get("metadata_json")) or {}
            out.append(
                {
                    "id": row.get("id"),
                    "app_id": raw_metadata.get("app_id"),
                    "page_name": raw_metadata.get("page_name"),
                    "element_name": raw_metadata.get("element_name"),
                    "source": raw_metadata.get("source"),
                    "chunk_text": row.get("document"),
                    "metadata": payload_metadata,
                    "similarity": float(row.get("similarity") or 0.0),
                }
            )
        return out

    async def upsert_rag_document(
        self,
        app_id: str,
        page_name: str,
        source: str,
        chunk_text: str,
        embedding: list[float] | None,
        element_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rag_documents (
                  app_id,
                  page_name,
                  element_name,
                  source,
                  chunk_text,
                  metadata
                )
                VALUES ($1,$2,$3,$4,$5,$6::jsonb)
                """,
                app_id,
                page_name,
                element_name,
                source,
                chunk_text,
                self._json_or_empty(metadata or {}),
            )
        if embedding:
            self._add_chroma_rag_document(
                app_id=app_id,
                page_name=page_name,
                source=source,
                chunk_text=chunk_text,
                embedding=embedding,
                element_name=element_name,
                metadata=metadata or {},
            )

    async def _upsert_element_rag_document(
        self,
        conn: Any,
        meta: ElementMeta,
        chunk_text: str,
        embedding: list[float] | None,
    ) -> None:
        if not chunk_text:
            return
        metadata = {
            "source": "element_meta",
            "strategy_id": meta.strategy_id,
            "field_type": meta.field_type,
            "tag": meta.signature.tag if meta.signature else "",
            "component_kind": meta.signature.component_kind if meta.signature else None,
            "prompt_compact_text": self._build_prompt_compact_text(meta),
            "fingerprint_tokens": self._fingerprint_tokens(meta),
            "locator": meta.last_good_locator.to_dict() if meta.last_good_locator else None,
            "robust_locator": meta.robust_locator.to_dict() if meta.robust_locator else None,
            "quality_metrics": dict(meta.quality_metrics or {}),
        }
        await conn.execute(
            """
            DELETE FROM rag_documents
            WHERE app_id=$1 AND page_name=$2 AND element_name=$3 AND source='element_meta'
            """,
            meta.app_id,
            meta.page_name,
            meta.element_name,
        )
        await conn.execute(
            """
            INSERT INTO rag_documents (
              app_id,
              page_name,
              element_name,
              source,
              chunk_text,
              metadata
            )
            VALUES ($1,$2,$3,$4,$5,$6::jsonb)
            """,
            meta.app_id,
            meta.page_name,
            meta.element_name,
            "element_meta",
            chunk_text,
            self._json_or_empty(metadata),
        )
        self._upsert_chroma_element_meta(meta=meta, chunk_text=chunk_text, embedding=embedding, metadata=metadata)

    def _upsert_chroma_element_meta(
        self,
        meta: ElementMeta,
        chunk_text: str,
        embedding: list[float] | None,
        metadata: dict[str, Any],
    ) -> None:
        try:
            rag_collection = self._get_chroma_rag_collection()
            elements_collection = self._get_chroma_elements_collection()
            rag_id = self._stable_chroma_id("element_meta", meta.app_id, meta.page_name, meta.element_name)
            element_id = self._stable_chroma_id("element", meta.app_id, meta.page_name, meta.element_name)

            if rag_collection is not None:
                if embedding:
                    rag_metadata = self._chroma_sanitize_metadata(
                        {
                            "app_id": meta.app_id,
                            "page_name": meta.page_name,
                            "element_name": meta.element_name,
                            "source": "element_meta",
                            "field_type": meta.field_type,
                            "metadata_json": self._json_or_empty(metadata),
                        }
                    )
                    rag_collection.upsert(
                        ids=[rag_id],
                        embeddings=[embedding],
                        documents=[chunk_text],
                        metadatas=[rag_metadata],
                    )
                else:
                    rag_collection.delete(ids=[rag_id])

            if elements_collection is None:
                return
            if embedding:
                payload = {
                    "app_id": meta.app_id,
                    "page_name": meta.page_name,
                    "element_name": meta.element_name,
                    "field_type": meta.field_type,
                    "last_good_locator_json": self._json_or_none(
                        meta.last_good_locator.to_dict() if meta.last_good_locator else None
                    )
                    or "",
                    "robust_locator_json": self._json_or_none(meta.robust_locator.to_dict() if meta.robust_locator else None)
                    or "",
                    "signature_json": self._json_or_none(meta.signature.to_dict() if meta.signature else None) or "",
                    "quality_metrics_json": self._json_or_empty(dict(meta.quality_metrics or {})),
                }
                element_metadata = self._chroma_sanitize_metadata(payload)
                elements_collection.upsert(
                    ids=[element_id],
                    embeddings=[embedding],
                    documents=[chunk_text],
                    metadatas=[element_metadata],
                )
            else:
                elements_collection.delete(ids=[element_id])
        except Exception as exc:
            LOGGER.warning("Chroma upsert failed for element metadata %s/%s/%s: %s", meta.app_id, meta.page_name, meta.element_name, exc)

    def _add_chroma_rag_document(
        self,
        app_id: str,
        page_name: str,
        source: str,
        chunk_text: str,
        embedding: list[float],
        element_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            rag_collection = self._get_chroma_rag_collection()
            if rag_collection is None:
                return
            document_id = str(uuid.uuid4())
            payload = self._chroma_sanitize_metadata(
                {
                    "app_id": app_id,
                    "page_name": page_name,
                    "element_name": element_name or "",
                    "source": source,
                    "field_type": str((metadata or {}).get("field_type") or ""),
                    "metadata_json": self._json_or_empty(metadata or {}),
                }
            )
            rag_collection.upsert(
                ids=[document_id],
                embeddings=[embedding],
                documents=[chunk_text],
                metadatas=[payload],
            )
        except Exception as exc:
            LOGGER.warning("Chroma upsert failed for rag document app=%s page=%s source=%s: %s", app_id, page_name, source, exc)

    def _get_chroma_rag_collection(self) -> Any | None:
        self._ensure_chroma_collections()
        return self._chroma_rag_collection

    def _get_chroma_elements_collection(self) -> Any | None:
        self._ensure_chroma_collections()
        return self._chroma_elements_collection

    def _ensure_chroma_collections(self) -> bool:
        if self._chroma_rag_collection is not None and self._chroma_elements_collection is not None:
            return True
        if chromadb is None:
            if not self._chroma_unavailable_logged:
                LOGGER.warning("ChromaDB is not installed. Install with: python -m pip install chromadb")
                self._chroma_unavailable_logged = True
            return False
        try:
            os.makedirs(self._chroma_path, exist_ok=True)
            if self._chroma_client is None:
                self._chroma_client = chromadb.PersistentClient(path=self._chroma_path)  # type: ignore[union-attr]
            self._chroma_rag_collection = self._chroma_client.get_or_create_collection(
                name=self._chroma_rag_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._chroma_elements_collection = self._chroma_client.get_or_create_collection(
                name=self._chroma_elements_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return True
        except Exception as exc:
            if not self._chroma_unavailable_logged:
                LOGGER.warning("ChromaDB init failed: %s", exc)
                self._chroma_unavailable_logged = True
            self._chroma_rag_collection = None
            self._chroma_elements_collection = None
            return False

    def _query_chroma_collection(
        self,
        collection: Any,
        query_embedding: list[float],
        limit: int,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
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
    def _chroma_where(filters: dict[str, str]) -> dict[str, Any] | None:
        clauses = [{key: value} for key, value in filters.items() if value]
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    @staticmethod
    def _stable_chroma_id(prefix: str, app_id: str, page_name: str, element_name: str) -> str:
        base = f"{prefix}::{app_id}::{page_name}::{element_name}"
        return base.replace(" ", "_")

    @staticmethod
    def _chroma_sanitize_metadata(payload: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, bool):
                sanitized[key] = value
                continue
            if isinstance(value, int):
                sanitized[key] = value
                continue
            if isinstance(value, float):
                sanitized[key] = float(value)
                continue
            sanitized[key] = str(value or "")
        return sanitized

    def _build_embedding_text(self, meta: ElementMeta) -> str:
        parts: list[str] = [
            f"app={meta.app_id}",
            f"page={meta.page_name}",
            f"element={meta.element_name}",
            f"field_type={meta.field_type}",
        ]
        if meta.signature:
            parts.append(f"tag={meta.signature.tag}")
            if meta.signature.component_kind:
                parts.append(f"component={meta.signature.component_kind}")
            if meta.signature.short_text:
                parts.append(f'label="{meta.signature.short_text}"')
            stable_attrs = [
                f"{key}={value}"
                for key, value in sorted((meta.signature.stable_attrs or {}).items())
                if str(key).strip() and str(value).strip()
            ]
            if stable_attrs:
                parts.append("attrs=" + " ".join(stable_attrs))
            if meta.signature.container_path:
                parts.append("parent=" + " > ".join(meta.signature.container_path[:6]))

        last_good_text = self._locator_fragment(meta.last_good_locator.to_dict() if meta.last_good_locator else None)
        if last_good_text:
            parts.append(f"last_good={last_good_text}")
        robust_text = self._locator_fragment(meta.robust_locator.to_dict() if meta.robust_locator else None)
        if robust_text:
            parts.append(f"robust={robust_text}")

        quality = dict(meta.quality_metrics or {})
        if quality:
            parts.extend(
                [
                    f"uniqueness={quality.get('uniqueness_score')}",
                    f"stability={quality.get('stability_score')}",
                    f"similarity={quality.get('similarity_score')}",
                    f"overall={quality.get('overall_score')}",
                ]
            )

        chunk = " | ".join(part for part in parts if part)
        limit = max(300, int(self._rag_doc_max_chars))
        if len(chunk) > limit:
            return chunk[: limit - 3] + "..."
        return chunk

    def _build_prompt_compact_text(self, meta: ElementMeta) -> str:
        tag = meta.signature.tag if meta.signature else ""
        label = meta.signature.short_text if meta.signature else ""
        parent = ""
        if meta.signature and meta.signature.container_path:
            parent = meta.signature.container_path[0]
        locator = self._locator_fragment(meta.last_good_locator.to_dict() if meta.last_good_locator else None)
        tokens = [
            f"E {meta.element_name}",
            f"T={tag}" if tag else "",
            f"FT={meta.field_type}",
            f'L="{label}"' if label else "",
            f"P={parent}" if parent else "",
            f"H={locator}" if locator else "",
        ]
        out = " ".join(token for token in tokens if token)
        if len(out) > 320:
            return out[:317] + "..."
        return out

    def _fingerprint_tokens(self, meta: ElementMeta) -> list[str]:
        out: list[str] = []
        out.append(f"field_type:{meta.field_type}")
        if meta.signature:
            if meta.signature.tag:
                out.append(f"tag:{meta.signature.tag}")
            if meta.signature.component_kind:
                out.append(f"component:{meta.signature.component_kind}")
            if meta.signature.short_text:
                out.append(f"text:{meta.signature.short_text.strip().casefold()[:40]}")
            for key, value in sorted((meta.signature.stable_attrs or {}).items()):
                if not key or not value:
                    continue
                out.append(f"attr:{key}={str(value).strip().casefold()[:40]}")
            if meta.signature.container_path:
                out.append(f"parent:{meta.signature.container_path[0]}")
        # Deduplicate while preserving order.
        dedup: list[str] = []
        seen: set[str] = set()
        for token in out:
            key = token.casefold()
            if key in seen:
                continue
            seen.add(key)
            dedup.append(token)
            if len(dedup) >= 16:
                break
        return dedup

    @staticmethod
    def _locator_fragment(locator_payload: Any) -> str:
        if not isinstance(locator_payload, dict):
            return ""
        kind = str(locator_payload.get("kind") or "").strip()
        value = str(locator_payload.get("value") or "").strip()
        if not kind or not value:
            return ""
        value = " ".join(value.split())
        if len(value) > 220:
            value = value[:217] + "..."
        return f"{kind}:{value}"

    async def _embed_text(self, text: str) -> list[float] | None:
        if not self._embedding_writes_enabled:
            return None
        payload = (text or "").strip()
        if not payload:
            return None
        embedder = await self._resolve_embedder()
        if embedder is None:
            return None
        try:
            vector = await embedder.embed_text(payload)
        except Exception as exc:
            LOGGER.warning("Embedding generation failed in repository upsert: %s", exc)
            return None
        if not vector:
            return None
        return self._normalize_vector_size(vector, self._embedding_dim)

    async def _resolve_embedder(self) -> Any | None:
        if self._embedder_resolved:
            return self._embedder
        self._embedder_resolved = True

        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key or "placeholder" in api_key.casefold() or api_key.startswith("<"):
            return None
        model = (os.getenv("XH_OPENAI_EMBED_MODEL") or "text-embedding-3-small").strip()
        try:
            from xpath_healer.rag.openai_embedder import OpenAIEmbedder

            self._embedder = OpenAIEmbedder(
                api_key=api_key,
                model=model,
                dimensions=self._embedding_dim,
            )
        except Exception as exc:
            LOGGER.warning("Embedding writer disabled: could not initialize OpenAI embedder (%s).", exc)
            self._embedder = None
        return self._embedder

    @staticmethod
    def _normalize_vector_size(vector: list[float], dim: int) -> list[float]:
        if dim <= 0:
            return [float(value) for value in vector]
        values = [float(value) for value in vector]
        if len(values) == dim:
            return values
        if len(values) > dim:
            return values[:dim]
        return values + [0.0] * (dim - len(values))

    @staticmethod
    def _safe_env_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().casefold() in {"1", "true", "yes", "on"}

    @staticmethod
    def _safe_env_int(name: str, default: int, minimum: int = 1) -> int:
        raw = os.getenv(name)
        if raw is None:
            return max(minimum, int(default))
        try:
            value = int(raw.strip())
        except Exception:
            return max(minimum, int(default))
        return max(minimum, value)

    @staticmethod
    def schema_sql() -> str:
        return """
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        CREATE TABLE IF NOT EXISTS page_index (
          page_id uuid PRIMARY KEY,
          app_id text NOT NULL,
          page_name text NOT NULL,
          dom_hash text NOT NULL,
          snapshot_version text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(app_id, page_name)
        );

        CREATE TABLE IF NOT EXISTS indexed_elements (
          id bigserial PRIMARY KEY,
          page_id uuid NOT NULL REFERENCES page_index(page_id) ON DELETE CASCADE,
          ordinal int NOT NULL DEFAULT 0,
          element_id text NOT NULL,
          element_name text,
          tag text,
          text text,
          normalized_text text,
          attr_id text,
          attr_name text,
          class_tokens jsonb NOT NULL DEFAULT '[]'::jsonb,
          role text,
          aria_label text,
          placeholder text,
          container_path text,
          parent_signature text,
          neighbor_text text,
          position_signature text,
          xpath text,
          css text,
          fingerprint_hash text,
          metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
        );

        CREATE TABLE IF NOT EXISTS elements (
          id uuid PRIMARY KEY,
          app_id text NOT NULL,
          page_name text NOT NULL,
          element_name text NOT NULL,
          field_type text NOT NULL,
          last_good_locator jsonb,
          robust_locator jsonb,
          strategy_id text,
          signature jsonb,
          hints jsonb,
          locator_variants jsonb,
          quality_metrics jsonb,
          last_seen timestamptz NOT NULL DEFAULT now(),
          success_count int NOT NULL DEFAULT 0,
          fail_count int NOT NULL DEFAULT 0,
          UNIQUE(app_id, page_name, element_name)
        );

        CREATE TABLE IF NOT EXISTS locator_variants (
          id bigserial PRIMARY KEY,
          element_id uuid NOT NULL REFERENCES elements(id) ON DELETE CASCADE,
          variant_key text NOT NULL,
          locator_kind text NOT NULL,
          locator_value text NOT NULL,
          locator_options jsonb NOT NULL DEFAULT '{}'::jsonb,
          locator_scope jsonb,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(element_id, variant_key)
        );

        CREATE TABLE IF NOT EXISTS quality_metrics (
          element_id uuid PRIMARY KEY REFERENCES elements(id) ON DELETE CASCADE,
          uniqueness_score double precision,
          stability_score double precision,
          similarity_score double precision,
          overall_score double precision,
          matched_count int,
          chosen_index int,
          strategy_id text,
          strategy_score double precision,
          locator_kind text,
          locator_value text,
          validation_reasons jsonb,
          valid_against_hints boolean,
          history jsonb,
          updated_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS events (
          id bigserial PRIMARY KEY,
          correlation_id text NOT NULL,
          timestamp timestamptz NOT NULL DEFAULT now(),
          app_id text,
          page_name text,
          element_name text,
          field_type text,
          stage text,
          status text,
          score double precision,
          details jsonb
        );

        CREATE TABLE IF NOT EXISTS healing_events (
          id bigserial PRIMARY KEY,
          run_id text NOT NULL,
          element_id uuid REFERENCES elements(id) ON DELETE SET NULL,
          app_id text,
          page_name text,
          element_name text,
          stage text,
          failure_type text,
          final_locator jsonb,
          outcome text,
          details jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS rag_documents (
          id bigserial PRIMARY KEY,
          app_id text NOT NULL,
          page_name text NOT NULL,
          element_name text,
          source text NOT NULL,
          chunk_text text NOT NULL,
          metadata jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_elements_lookup
          ON elements (app_id, page_name, element_name);

        CREATE INDEX IF NOT EXISTS idx_page_index_lookup
          ON page_index (app_id, page_name, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_indexed_elements_page
          ON indexed_elements (page_id, ordinal);

        CREATE INDEX IF NOT EXISTS idx_elements_page_field
          ON elements (app_id, page_name, field_type, success_count DESC, last_seen DESC);

        CREATE INDEX IF NOT EXISTS idx_locator_variants_element_key
          ON locator_variants (element_id, variant_key);

        CREATE INDEX IF NOT EXISTS idx_events_corr
          ON events (correlation_id, timestamp DESC);

        CREATE INDEX IF NOT EXISTS idx_healing_events_run
          ON healing_events (run_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_rag_documents_scope
          ON rag_documents (app_id, page_name, element_name, created_at DESC);
        """

    @staticmethod
    def _json_or_none(payload: Any) -> str | None:
        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=True, default=str)

    @staticmethod
    def _json_or_empty(payload: Any) -> str:
        if payload is None:
            payload = {}
        return json.dumps(payload, ensure_ascii=True, default=str)

    @staticmethod
    def _safe_uuid_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return str(uuid.UUID(text))
        except Exception:
            return None

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

    @classmethod
    def _row_to_payload(cls, row: Any) -> dict[str, Any]:
        last_seen = row.get("last_seen")
        if isinstance(last_seen, datetime):
            last_seen_text = last_seen.isoformat()
        else:
            last_seen_text = str(last_seen or datetime.now(UTC).isoformat())
        return {
            "id": str(row["id"]),
            "app_id": str(row["app_id"]),
            "page_name": str(row["page_name"]),
            "element_name": str(row["element_name"]),
            "field_type": str(row["field_type"]),
            "last_good_locator": cls._decode_json(row.get("last_good_locator")),
            "robust_locator": cls._decode_json(row.get("robust_locator")),
            "strategy_id": row.get("strategy_id"),
            "signature": cls._decode_json(row.get("signature")),
            "hints": cls._decode_json(row.get("hints")),
            "locator_variants": cls._decode_json(row.get("locator_variants")) or {},
            "quality_metrics": cls._decode_json(row.get("quality_metrics")) or {},
            "last_seen": last_seen_text,
            "success_count": int(row.get("success_count") or 0),
            "fail_count": int(row.get("fail_count") or 0),
        }

    async def _load_locator_variants(self, conn: Any, element_id: str) -> dict[str, Any]:
        rows = await conn.fetch(
            """
            SELECT variant_key, locator_kind, locator_value, locator_options, locator_scope
            FROM locator_variants
            WHERE element_id=$1::uuid
            """,
            element_id,
        )
        out: dict[str, Any] = {}
        for row in rows:
            item = {
                "kind": str(row["locator_kind"]),
                "value": str(row["locator_value"]),
                "options": self._decode_json(row.get("locator_options")) or {},
                "scope": self._decode_json(row.get("locator_scope")),
            }
            out[str(row["variant_key"])] = item
        return out

    async def _load_quality_metrics(self, conn: Any, element_id: str) -> dict[str, Any]:
        row = await conn.fetchrow(
            """
            SELECT
              uniqueness_score,
              stability_score,
              similarity_score,
              overall_score,
              matched_count,
              chosen_index,
              strategy_id,
              strategy_score,
              locator_kind,
              locator_value,
              validation_reasons,
              valid_against_hints,
              history
            FROM quality_metrics
            WHERE element_id=$1::uuid
            LIMIT 1
            """,
            element_id,
        )
        if not row:
            return {}
        return {
            "uniqueness_score": row.get("uniqueness_score"),
            "stability_score": row.get("stability_score"),
            "similarity_score": row.get("similarity_score"),
            "overall_score": row.get("overall_score"),
            "matched_count": row.get("matched_count"),
            "chosen_index": row.get("chosen_index"),
            "strategy_id": row.get("strategy_id"),
            "strategy_score": row.get("strategy_score"),
            "locator_kind": row.get("locator_kind"),
            "locator_value": row.get("locator_value"),
            "validation_reasons": self._decode_json(row.get("validation_reasons")) or [],
            "valid_against_hints": row.get("valid_against_hints"),
            "history": self._decode_json(row.get("history")) or [],
        }

    async def _sync_locator_variants(self, conn: Any, element_id: str, variants: dict[str, Any]) -> None:
        await conn.execute("DELETE FROM locator_variants WHERE element_id=$1::uuid", element_id)
        if not variants:
            return
        for key, item in variants.items():
            if not isinstance(item, dict):
                continue
            await conn.execute(
                """
                INSERT INTO locator_variants (
                  element_id,
                  variant_key,
                  locator_kind,
                  locator_value,
                  locator_options,
                  locator_scope,
                  updated_at
                )
                VALUES ($1::uuid,$2,$3,$4,$5::jsonb,$6::jsonb,now())
                """,
                element_id,
                str(key),
                str(item.get("kind") or "css"),
                str(item.get("value") or ""),
                self._json_or_empty(item.get("options") or {}),
                self._json_or_none(item.get("scope")),
            )

    async def _sync_quality_metrics(self, conn: Any, element_id: str, metrics: dict[str, Any]) -> None:
        if not isinstance(metrics, dict):
            metrics = {}
        await conn.execute(
            """
            INSERT INTO quality_metrics (
              element_id,
              uniqueness_score,
              stability_score,
              similarity_score,
              overall_score,
              matched_count,
              chosen_index,
              strategy_id,
              strategy_score,
              locator_kind,
              locator_value,
              validation_reasons,
              valid_against_hints,
              history,
              updated_at
            )
            VALUES (
              $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14::jsonb,now()
            )
            ON CONFLICT (element_id)
            DO UPDATE SET
              uniqueness_score = EXCLUDED.uniqueness_score,
              stability_score = EXCLUDED.stability_score,
              similarity_score = EXCLUDED.similarity_score,
              overall_score = EXCLUDED.overall_score,
              matched_count = EXCLUDED.matched_count,
              chosen_index = EXCLUDED.chosen_index,
              strategy_id = EXCLUDED.strategy_id,
              strategy_score = EXCLUDED.strategy_score,
              locator_kind = EXCLUDED.locator_kind,
              locator_value = EXCLUDED.locator_value,
              validation_reasons = EXCLUDED.validation_reasons,
              valid_against_hints = EXCLUDED.valid_against_hints,
              history = EXCLUDED.history,
              updated_at = now()
            """,
            element_id,
            metrics.get("uniqueness_score"),
            metrics.get("stability_score"),
            metrics.get("similarity_score"),
            metrics.get("overall_score"),
            metrics.get("matched_count"),
            metrics.get("chosen_index"),
            metrics.get("strategy_id"),
            metrics.get("strategy_score"),
            metrics.get("locator_kind"),
            metrics.get("locator_value"),
            self._json_or_empty(metrics.get("validation_reasons") or []),
            metrics.get("valid_against_hints"),
            self._json_or_empty(metrics.get("history") or []),
        )
