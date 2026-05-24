Title: Database and Storage Layer Method and Interface Prompts

Mandatory reference:
- `prompts/final_solution_pack/08_Algorithm_Inventory.md` (sections 6 and 7)

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
3. `upsert_rag_document` / rag-document methods
- Store/update retrievable metadata chunks.
4. Chroma sync methods
- Keep element/rag vectors updated in Chroma collections.
5. `_embed_text` and `_resolve_embedder`
- Generate embeddings only when enabled/available.

Dual repository methods and intent:
1. `find`
- DB-first read; fallback read on failure or policy miss.
2. `upsert`
- Write to primary with resilient backup write path.
3. `log_event`
- Preserve observability when one backend fails.
4. `close`
- Close both backends safely.

JSON repository methods and intent:
1. `_read_page_file` and `_write_page_file`
- Preserve stable metadata JSON schema.
2. `log_event`
- Append event stream safely to JSONL.

Required metadata JSON contract:
1. root keys: app_id, page_name, elements, page_index
2. `elements[element_name]` stores serialized ElementMeta fields including locators/signature/hints/variants/quality/counters

High-level behavior example:
1. Primary DB reachable -> reads/writes served by DB, mirrored to JSON backup.
2. Primary unavailable -> JSON fallback still serves metadata; operations logged with backend status.
