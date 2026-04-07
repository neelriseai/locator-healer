Master Design - XPath Healer (Code-Accurate Baseline)

1. Project overview

XPath Healer is a Python deterministic-first locator recovery library with optional RAG/LLM fallback.
It is library-first (`xpath_healer/*`) with adapter-specific facades and a thin FastAPI wrapper (`service/main.py`).
It supports two automation adapters:
1. `playwright_python` (native async path)
2. `selenium_python` (sync webdriver calls wrapped with `asyncio.to_thread`)

Storage/runtime model:
1. Metadata repository: Postgres primary + JSON fallback via `DualMetadataRepository` (or memory when DSN is absent)
2. Vector retrieval: Chroma collections (`xh_rag_documents`, `xh_elements`)
3. RAG retriever in active flow: `ChromaRetriever` (pgvector name only exists as compatibility alias)

2. Runtime execution model

Stage order in `HealingService.recover_locator(...)`:
1. `fallback`
2. `metadata`
3. `rules`
4. `fingerprint`
5. `page_index`
6. `signature`
7. `dom_mining`
8. `defaults`
9. `position`
10. `rag`

Stage gating:
1. Global profile and per-stage flags come from `HealerConfig.from_env`.
2. `XH_STAGE_PROFILE=llm_only` disables deterministic stages and leaves `rag=true`.
3. Per-stage flags (`XH_STAGE_*_ENABLED`) can override profile defaults.

Concurrency model (code-accurate):
1. Stage pipeline is sequential.
2. Candidate validation is parallel for:
   - metadata
   - rules
   - fingerprint
   - page_index
   - defaults
   using `asyncio.gather` in `_evaluate_candidates_parallel(...)`.
3. Candidate validation is sequential for:
   - fallback
   - signature
   - dom_mining
   - position
   - rag
4. Selenium adapter executes blocking webdriver operations in worker threads with `asyncio.to_thread`.
5. Playwright adapter remains async-native (no thread offload needed for core operations).

3. Retry model

There are three retry surfaces:
1. Validation retry (core):
   - `_validate_candidate_with_retry(...)`
   - env: `XH_RETRY_ENABLED`, `XH_RETRY_MAX_ATTEMPTS`, `XH_RETRY_DELAY_MS`, `XH_RETRY_REASON_CODES`
2. RAG deep retry (reason-based, bounded):
   - triggered by `_rag_retry_reason(...)`
   - env: `XH_PROMPT_GRAPH_DEEP_RETRY_ENABLED`, `XH_PROMPT_GRAPH_DEEP_RETRY_MAX`
3. Embedding fallback retry:
   - `OpenAIEmbedder.embed_text(...)` retries once without `dimensions` on failure

4. RAG activation and provider wiring

RAG path is enabled only when all are true:
1. `XH_RAG_ENABLED=true`
2. `XH_STAGE_RAG_ENABLED=true`
3. LLM key present (`XH_OPENAI_LLM_API_KEY` or `OPENAI_API_KEY`)
4. Embed key present (`XH_OPENAI_EMBED_API_KEY` or `OPENAI_API_KEY`)
5. `XH_PG_DSN` configured (required by current facade wiring)

Provider routing:
1. `XH_OPENAI_PROVIDER=openai|azure`
2. OpenAI: key + model vars
3. Azure: endpoint/version/deployment vars for chat and embed, with shared fallbacks

5. Core modules and responsibilities

Primary flow:
1. `xpath_healer/api/base.py`
   - facade runtime entry
   - env-based repository and RAG initialization
2. `xpath_healer/core/healing_service.py`
   - ordered orchestration, stage tracing, retry, persistence hooks
3. `xpath_healer/core/validator.py`
   - match-count, visibility, enabled, geometry/axis gating
4. `xpath_healer/store/*`
   - repository abstraction and backends
5. `xpath_healer/rag/*`
   - embedding, retrieval, prompt construction, parsing, anti-hallucination filtering
6. `adapters/playwright_python/*`, `adapters/selenium_python/*`
   - framework-specific locator resolution/runtime operations

6. Dependencies baseline

Package truth sources:
1. `pyproject.toml`
2. `requirements.txt`

Current groups:
1. Core runtime: `fastapi`, `uvicorn`, `playwright`, `selenium`
2. Similarity/DOM: `rapidfuzz`, `beautifulsoup4`, `lxml`
3. DB/vector: `asyncpg`, `chromadb`
4. LLM: `openai`
5. Test: `pytest`, `pytest-asyncio`, `pytest-bdd`

7. Configuration source of truth

Use these files as canonical mapping:
1. `xpath_healer/core/config.py` (core stage/retry/validator/fingerprint policy)
2. `xpath_healer/api/base.py` (RAG/repository/provider env wiring)
3. `tests/integration/settings.py` and `tests/integration/conftest.py` (integration/browser/artifact envs)
4. `.env.example` (documented defaults)
5. `prompts/final_solution_pack/03_Configuration_Catalog.md` (human-readable config matrix)

8. Regeneration contract

When recreating the project:
1. Preserve exact stage order and names.
2. Preserve sequential stage orchestration and selective parallel candidate validation.
3. Preserve Selenium thread-offload behavior (`asyncio.to_thread`) and Playwright async behavior.
4. Keep Chroma as active retriever path.
5. Keep config/env keys exactly aligned with code.
6. Never auto-accept LLM suggestions without validator pass.
