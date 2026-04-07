Title: Database and Storage Layer Architecture Prompt

Layer objective:
- Provide durable metadata persistence, event logging, page-index storage, and Chroma-backed vector retrieval integration.

Mandatory reference:
- `prompts/final_solution_pack/08_Algorithm_Inventory.md` (sections 6 and 7)

Use this prompt with AI assistant:

1. Build storage around `MetadataRepository` interface.
2. Support four backends:
   - in-memory
   - JSON file
   - PostgreSQL
   - Dual repository (DB-first, JSON fallback)
3. Ensure DB-first read policy with fallback on primary error/miss as implemented.
4. Ensure resilient dual-write behavior with explicit operation status logging.
5. Keep Postgres schema aligned to current tables and indexes.
6. Keep vector retrieval backend Chroma (collections `xh_rag_documents`, `xh_elements`).
7. Keep async behavior and bounded pool lifecycle.

Required schema contracts:
1. Postgres tables:
   - page_index
   - indexed_elements
   - elements
   - locator_variants
   - quality_metrics
   - events
   - healing_events
   - rag_documents
2. Keep lookup indexes used by current query patterns.
3. Keep Postgres metadata/chunk store plus Chroma vector sync model.

Required JSON fallback contracts:
1. File layout:
   - `artifacts/metadata/<app_id>/<page_name>.json`
   - `artifacts/metadata/events.jsonl`
2. Page JSON shape includes root keys and serialized `ElementMeta` payloads.
3. Dual repo read-through/warm-up behavior must remain intact.

Primary files to target:
1. `xpath_healer/store/repository.py`
2. `xpath_healer/store/memory_repository.py`
3. `xpath_healer/store/json_repository.py`
4. `xpath_healer/store/pg_repository.py`
5. `xpath_healer/store/dual_repository.py`

Acceptance criteria:
1. CRUD and event logging work through interface.
2. Page index read/write works for structured DOM candidates.
3. Chroma retrieval path returns candidates when vectors exist.
4. Fallback behavior does not hide primary failure traces.
