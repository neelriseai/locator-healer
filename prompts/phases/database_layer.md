Title: Phase Prompt - Database Layer (Postgres + ChromaDB + JSON fallback)

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Implement and validate repository-backed persistence with DB-first and JSON fallback behavior.

Prompt to use with AI assistant:

```
Implement the database layer for XPath Healer.

Scope files:
- xpath_healer/store/repository.py
- xpath_healer/store/pg_repository.py
- xpath_healer/store/json_repository.py
- xpath_healer/store/dual_repository.py
- xpath_healer/store/memory_repository.py

Schema requirements:
- Extension: pgcrypto
- Tables: page_index, indexed_elements, elements, locator_variants, quality_metrics, events, healing_events, rag_documents
- Keep vector-state writes/lookup routed to Chroma collections (`xh_rag_documents`, `xh_elements`).
- Add lookup indexes used by current Postgres queries.

Repository requirements:
1. CRUD for element metadata (find/upsert).
2. Persist/query page index structures.
3. Persist stage events and healing outcomes.
4. Persist/query RAG document metadata used by Chroma retrieval flows.
5. Dual repository behavior:
   - primary: Postgres
   - fallback: JSON
   - read/write behavior must tolerate primary failures.

Environment requirements:
- XH_PG_DSN
- XH_PG_POOL_MIN / XH_PG_POOL_MAX
- XH_PG_AUTO_INIT_SCHEMA
- XH_METADATA_JSON_DIR
- XH_CHROMA_PATH
- XH_CHROMA_RAG_COLLECTION
- XH_CHROMA_ELEMENTS_COLLECTION
- XH_EMBEDDING_WRITE_ENABLED
- XH_RAG_DOC_MAX_CHARS

Deliverables:
- SQL schema function (`schema_sql`) and init workflow.
- Repository methods with async behavior.
- Unit tests for schema and repository behavior.
```

Acceptance criteria:
- Postgres repository connects and passes CRUD tests.
- Dual repository logs DB operation outcomes and falls back gracefully.
- JSON metadata remains available as backup path.
- Postgres metadata and Chroma retrieval integration run together without schema drift.

Validation commands:
- `python -m pytest -q tests/unit/test_pg_repository_schema.py`
- `python -m pytest -q tests/unit/test_dual_repository.py`
