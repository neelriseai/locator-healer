Title: Database and Storage Layer Unit Test and Debugging Prompts

Use this prompt with AI assistant:

Unit test prompts:

1. Repository contract tests
- Verify every backend can perform `find`, `upsert`, and `log_event`.

2. Postgres schema tests
- Verify schema includes required tables, constraints, and vector indexes.

3. Dual repository tests
- Verify primary success path.
- Verify primary failure fallback path.
- Verify read/write status logging.

4. JSON repository tests
- Verify page file persistence for metadata and page index.
- Verify event persistence format.

5. Embedding write control tests
- Verify vector writes are skipped when disabled.
- Verify embedding dimension normalization.

Debugging prompt:
1. If DB miss occurs for known element:
   - check key normalization (`app_id`, `page_name`, `element_name`)
   - check write path status in logs
   - check fallback JSON for same key.
2. If vector counts are zero:
   - verify embedding write flag
   - verify API key presence
   - verify embedder initialization path.
3. If schema errors occur:
   - check extension availability
   - check vector type and index syntax compatibility.

Preferred test commands:
1. `python -m pytest -q tests/unit/test_pg_repository_schema.py`
2. `python -m pytest -q tests/unit/test_dual_repository.py`
3. `python -m pytest -q tests/unit/test_facade_repository_init.py`

Acceptance criteria:
1. Backends are contract-compatible.
2. Failure behavior is explicit and observable.
3. Data remains queryable for later stages.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

