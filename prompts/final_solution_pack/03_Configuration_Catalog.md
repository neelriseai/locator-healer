Title: Unified Configuration Catalog Across All Layers

Purpose:
- Keep all configurable behavior documented in one place.

Core and stage policy (`XH_*`):
1. `XH_STAGE_PROFILE`
   - `full`: deterministic + optional rag
   - `llm_only`: deterministic disabled, rag-only
2. `XH_STAGE_FALLBACK_ENABLED`
3. `XH_STAGE_METADATA_ENABLED`
4. `XH_STAGE_RULES_ENABLED`
5. `XH_STAGE_FINGERPRINT_ENABLED`
6. `XH_STAGE_PAGE_INDEX_ENABLED`
7. `XH_STAGE_SIGNATURE_ENABLED`
8. `XH_STAGE_DOM_MINING_ENABLED`
9. `XH_STAGE_DEFAULTS_ENABLED`
10. `XH_STAGE_POSITION_ENABLED`
11. `XH_STAGE_RAG_ENABLED`

RAG and LLM:
1. `XH_RAG_ENABLED`
2. `XH_RAG_TOP_K`
3. `XH_RAG_PROMPT_TOP_N`
4. `XH_OPENAI_MODEL`
5. `XH_OPENAI_EMBED_MODEL`
6. `XH_OPENAI_EMBED_DIM`
7. `XH_PROMPT_GRAPH_DEEP_DEFAULT`
8. `XH_PROMPT_GRAPH_DEEP_RETRY_ENABLED`
9. `XH_PROMPT_GRAPH_DEEP_RETRY_MAX`
10. `XH_LLM_MIN_CONFIDENCE_FOR_ACCEPT`
11. `OPENAI_API_KEY`

Storage and DB:
1. `XH_PG_DSN`
2. `XH_PG_POOL_MIN`
3. `XH_PG_POOL_MAX`
4. `XH_PG_AUTO_INIT_SCHEMA`
5. `XH_METADATA_JSON_DIR`
6. `XH_EMBEDDING_WRITE_ENABLED`
7. `XH_RAG_DOC_MAX_CHARS`

Validator and scoring:
1. `XH_SIMILARITY_THRESHOLD`
2. `XH_VALIDATOR_REQUIRE_VISIBLE`
3. `XH_VALIDATOR_REQUIRE_ENABLED`
4. `XH_VALIDATOR_STRICT_SINGLE_MATCH`
5. `XH_VALIDATOR_GEOMETRY_ENABLED`
6. `XH_VALIDATOR_GEOMETRY_TOLERANCE`
7. `XH_VALIDATOR_AXIS_ENABLED`

Fingerprint:
1. `XH_FINGERPRINT_ENABLED`
2. `XH_FINGERPRINT_MIN_SCORE`
3. `XH_FINGERPRINT_ACCEPT_SCORE`
4. `XH_FINGERPRINT_CANDIDATE_LIMIT`

Retry:
1. `XH_RETRY_ENABLED`
2. `XH_RETRY_MAX_ATTEMPTS`
3. `XH_RETRY_DELAY_MS`
4. `XH_RETRY_REASON_CODES`

Logging:
1. `XH_LOG_LEVEL`

Integration execution settings:
1. `XH_BASE_URL`
2. `XH_BROWSER_ENGINE`
3. `XH_BROWSER_CHANNEL`
4. `XH_HEADLESS`
5. `XH_ARTIFACTS_ROOT`
6. `XH_REPORTS_DIR`
7. `XH_LOGS_DIR`
8. `XH_SCREENSHOTS_DIR`
9. `XH_VIDEOS_DIR`
10. `XH_METADATA_DIR`
11. `XH_JUNIT_XML`
12. `XH_CUCUMBER_JSON`
13. `XH_STEP_REPORT`
14. `XH_HEALING_CALLS_REPORT`
15. `XH_HTML_REPORT`
16. `XH_SCREENSHOT_EACH_TEST`
17. `XH_SCREENSHOT_ON_FAILURE`
18. `XH_SCREENSHOT_EACH_STEP`
19. `XH_VIDEO_EACH_TEST`
20. `XH_VIDEO_WIDTH`
21. `XH_VIDEO_HEIGHT`

Configuration files:
1. `.env` or `.env.example` for shared defaults
2. `tests/integration/config.json` for integration profile defaults
3. `pyproject.toml` for test settings and markers

Recommended policy:
1. Keep non-secret defaults in `.env.example`.
2. Keep secrets in user-level environment variables.
3. Keep environment-specific files per machine and avoid hardcoding local credentials.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

