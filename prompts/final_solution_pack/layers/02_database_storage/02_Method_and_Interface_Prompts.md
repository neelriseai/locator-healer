Title: Database and Storage Layer Method and Interface Prompts

Use this prompt with AI assistant:

Interface methods to implement consistently in every backend:
1. `find(app_id, page_name, element_name)`
2. `upsert(meta)`
3. `find_candidates_by_page(app_id, page_name, field_type, limit)`
4. `get_page_index(app_id, page_name)`
5. `upsert_page_index(page_index)`
6. `log_event(event)`

Postgres-specific methods and intent:
1. `connect` / `close` / `init_schema`
- Manage pool lifecycle and schema bootstrap.
2. `schema_sql`
- Provide full DDL for tables, constraints, and indexes.
3. `search_rag_documents`
- Retrieve top semantic matches by vector similarity.
4. `upsert_rag_document`
- Store/update document chunks and embeddings.
5. `_upsert_element_rag_document`
- Keep element-level RAG chunk synced with metadata upsert.
6. `_embed_text` and `_resolve_embedder`
- Generate embedding only when enabled and adapter available.

Dual repository methods and intent:
1. `find`
- DB-first read; fallback read on failure or miss when policy requires.
2. `upsert`
- Write to primary; keep backup write path resilient.
3. `log_event`
- Preserve observability even when one backend fails.
4. `close`
- Close both backends safely.

JSON repository methods and intent:
1. `_read_page_file` and `_write_page_file`
- Keep file format stable and durable.
2. `log_event`
- Append event stream safely to JSONL.

High-level behavior example:
1. Primary DB is reachable -> all reads/writes handled by DB and mirrored to JSON backup.
2. Primary DB is unavailable -> fallback JSON still serves metadata and logs operation status.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

