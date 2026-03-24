Title: Phase Prompt - Database Layer (Postgres + pgvector + JSON fallback)

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Implement and validate repository-backed persistence with DB-first and JSON fallback behavior.

Prompt to use with AI assistant:

```
Implement the database layer for XPath Healer per `prompts/01_Master_Design_for_xpath_healer.md`.

Scope files:
- xpath_healer/store/repository.py
- xpath_healer/store/pg_repository.py
- xpath_healer/store/json_repository.py
- xpath_healer/store/dual_repository.py
- xpath_healer/store/memory_repository.py

Schema requirements:
- Extensions: vector, pgcrypto
- Tables: page_index, indexed_elements, elements, locator_variants, quality_metrics, events, healing_events, rag_documents
- Vector columns:
  - elements.signature_embedding vector(1536)
  - rag_documents.embedding vector(1536)
- Add lookup and ivfflat indexes used by current queries.

Repository requirements:
1. CRUD for element metadata (find/upsert).
2. Persist and query page index structures.
3. Persist stage events and healing outcomes.
4. Support vector-based candidate search for RAG documents.
5. Dual repository behavior:
   - primary: Postgres
   - fallback: JSON
   - read/write behavior must tolerate primary failures.

Environment requirements:
- XH_PG_DSN
- XH_PG_POOL_MIN / XH_PG_POOL_MAX
- XH_PG_AUTO_INIT_SCHEMA
- XH_METADATA_JSON_DIR
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
- pgvector queries run when embeddings are present.

Validation commands:
- `python -m pytest -q tests/unit/test_pg_repository_schema.py`
- `python -m pytest -q tests/unit/test_dual_repository.py`
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

