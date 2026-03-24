Title: Database and Storage Layer Architecture Prompt

Layer objective:
- Provide durable metadata persistence, event logging, page indexing storage, and vector retrieval support.

Use this prompt with AI assistant:

1. Build storage around `MetadataRepository` interface.
2. Support four backends:
   - in-memory
   - JSON file
   - PostgreSQL
   - Dual repository (DB-first, JSON fallback)
3. Ensure DB-first read policy with fallback when primary read fails.
4. Ensure write attempts to primary and backup as configured.
5. Keep schema compatible with vector search for `elements` and `rag_documents`.
6. Keep async behavior and bounded connection pooling.

Primary files to target:
1. `xpath_healer/store/repository.py`
2. `xpath_healer/store/memory_repository.py`
3. `xpath_healer/store/json_repository.py`
4. `xpath_healer/store/pg_repository.py`
5. `xpath_healer/store/dual_repository.py`

Acceptance criteria:
1. CRUD and event logging work through interface.
2. Page index read/write works for structured DOM candidates.
3. Vector search returns candidates when embeddings exist.
4. Fallback behavior does not hide primary failure traces.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

