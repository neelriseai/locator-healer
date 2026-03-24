Master Design - XPath Healer (Current Solution Baseline)

1. Project Overview

XPath Healer is a Python, deterministic-first locator healing framework with optional RAG/LLM recovery.
It is library-first (`xpath_healer/*`) with a thin FastAPI wrapper (`service/main.py`) and Playwright BDD integration tests (`tests/integration/*`).
When a locator breaks, the system runs a staged healing cascade, validates candidates on live DOM, scores quality, persists metadata, and emits traceable logs.
Storage is dual-mode: Postgres primary plus JSON fallback backup.
Vector retrieval is backed by ChromaDB, while `PgVectorRetriever` is kept as a compatibility alias.
RAG is optional and is used as final fallback unless stage profile is explicitly set to `llm_only`.

2. Core Principles

Architecture Principles

1. Deterministic-first by default
   Healing runs deterministic stages before LLM unless `XH_STAGE_PROFILE=llm_only`.

2. Layered and pluggable
   Core, store, service, and RAG layers are decoupled with interfaces and stage flags.

3. Validator-gated acceptance
   A candidate is accepted only after runtime validation (visibility/enabled/single-match intent).

4. Observability-first
   Every stage emits structured trace events (`recover_start`, `rag_context`, `rag`, `rag_retry`, `rag_hallucination`, `recover_end`).

5. Reproducibility
   Same env flags + same prompts should regenerate same package structure and behavior.

6. Safe secret handling
   API key/DSN are read from environment; never hardcode secrets in source.

3. System Layers

System Layers

1. Core Healing Layer (`xpath_healer/core`)
   Orchestrates healing stages, candidate generation, ranking/scoring, validation, retries, and persistence hooks.

2. DOM and Context Layer (`xpath_healer/dom`, `xpath_healer/core/page_index.py`, `xpath_healer/core/signature.py`)
   Captures DOM snapshot, mines robust selectors, builds signatures/fingerprints/page index.

3. Storage Layer (`xpath_healer/store`)
   Repository abstraction with in-memory, JSON, Postgres, and dual-write/dual-read repository behavior.

4. RAG/Model Layer (`xpath_healer/rag`)
   Embedding, retrieval (ChromaDB), compact DSL prompt construction, LLM suggestion parsing, anti-hallucination checks.

5. Service Layer (`service/main.py`)
   FastAPI endpoints: `/health`, `/generate`, `/heal`.

6. Framework Integration Layer (`tests/integration`)
   Pytest-BDD + Playwright suite validates real healing paths, screenshots, logs, JSON/JUnit/Cucumber reports.

4. High-Level Healing Flow

Healing Flow (runtime)

1. Test action fails due to broken fallback locator.
2. `XPathHealerFacade.recover_locator(...)` builds `BuildInput` and forwards to `HealingService.recover_locator(...)`.
3. Service resolves hints + existing metadata and emits `recover_start`.
4. Stage cascade executes (when enabled):
   `fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag`.
5. Each stage emits trace entries and validation results; parallel evaluation is used for selected stages.
6. RAG stage (if enabled and adapters configured):
   build compact DOM signature + DSL prompt -> embed query -> retrieve candidates -> rerank -> LLM suggest -> parse/dedupe/hallucination checks -> validate.
7. If accepted, metadata is updated (`last_good_locator`, `robust_locator`, variants, quality metrics, counters) and `recover_end` success is logged.
8. If all fail, failure counters/events are persisted and `recover_end` fail is logged.

5. Module Responsibilities

Core Modules

- `xpath_healer/api/facade.py`
  - `XPathHealerFacade.recover_locator(...)`: main entry for runtime healing.
  - `XPathHealerFacade.generate_locator_async(...)`: authoring-time deterministic locator generation.
  - `_build_repository_from_env()`: in-memory vs dual Postgres+JSON repo.
  - `_build_rag_assist_from_env()`: wires `OpenAIEmbedder`, `PgVectorRetriever`, `OpenAILLM`, `RagAssist`.

- `xpath_healer/core/healing_service.py`
  - `HealingService.recover_locator(...)`: master stage orchestrator.
  - `_evaluate_candidates(...)` and `_evaluate_candidates_parallel(...)`: validation + tracing.
  - `_validate_candidate_with_retry(...)`: lightweight retry for transient reason codes.
  - `_stage_enabled(...)`: per-stage runtime toggles.

- `xpath_healer/core/builder.py` + `xpath_healer/core/strategies/*`
  - Strategy registry and candidate construction for rules/defaults/position classes.
  - Key deterministic strategies include:
    `GenericTemplateStrategy`, `AxisHintFieldResolverStrategy`, `CompositeLabelControlStrategy`,
    `CheckboxIconByLabelStrategy`, `ButtonTextCandidateStrategy`, `MultiFieldTextResolverStrategy`,
    `AttributeStrategy`, `GridCellByColIdStrategy`, `TextOccurrenceStrategy`, `PositionFallbackStrategy`.

- `xpath_healer/core/validator.py`
  - `XPathValidator.validate_candidate(...)`: runtime gating for match count, visibility, enabled-state, axis/geometry checks.

- `xpath_healer/core/signature.py`, `fingerprint.py`, `similarity.py`, `page_index.py`
  - Signature extraction, fingerprint matching, quality scoring, and page-level indexing utilities.

Storage Modules

- `xpath_healer/store/repository.py`: repository interface contract.
- `xpath_healer/store/memory_repository.py`: standalone mode backend.
- `xpath_healer/store/json_repository.py`: local metadata backup (`artifacts/metadata`).
- `xpath_healer/store/pg_repository.py`: Postgres backend with Chroma collection sync hooks.
- `xpath_healer/store/dual_repository.py`: DB-first + JSON fallback behavior.

RAG Modules

- `xpath_healer/rag/rag_assist.py`
  - `suggest(...)`: retrieve + prompt + LLM suggest + parse/ground/dedupe.
- `xpath_healer/rag/prompt_builder.py` and `prompt_dsl.py`
  - Compact, graph-aware prompt payload with DOM signature and constrained candidate context.
- `xpath_healer/rag/openai_embedder.py`, `openai_llm.py`, `chroma_retriever.py`, `pgvector_retriever.py`
  - Provider adapters for embeddings/chat and vector retrieval.

Service Modules

- `service/main.py`
  - `create_app(...)`, `/generate`, `/heal` endpoints, request/response Pydantic models.

Data Contract (Postgres Schema)

- Extensions: `pgcrypto`
- Tables:
  - `elements`
    - locator/signature state per element (`last_good_locator`, `robust_locator`, counters, quality metadata).
  - `locator_variants`
    - normalized locator variants keyed by `variant_key`.
  - `quality_metrics`
    - uniqueness/stability/similarity/overall and validation info.
  - `page_index`
    - page snapshot identity (`app_id`, `page_name`, `dom_hash`).
  - `indexed_elements`
    - mined page elements and structural attributes (`xpath`, `css`, `fingerprint_hash`, metadata).
  - `events`
    - stage-level trace logs.
  - `healing_events`
    - run-oriented healing outcomes.
  - `rag_documents`
    - retrievable chunks + metadata for RAG context.

Vector Store (ChromaDB)

- Collections:
  - `xh_rag_documents`
  - `xh_elements`
- Default local path:
  - `artifacts/chroma` (configurable via `XH_CHROMA_PATH`)
- Collection bootstrap:
  - Auto-created by `PostgresMetadataRepository._ensure_chroma_collections()`.

6. Project Structure

Recommended Current Structure

xpath-healer/
 - xpath_healer/
   - api/
     - facade.py
   - core/
     - config.py
     - healing_service.py
     - validator.py
     - builder.py
     - signature.py
     - fingerprint.py
     - similarity.py
     - page_index.py
     - models.py
     - strategy_registry.py
     - strategies/
   - dom/
     - snapshot.py
     - mine.py
   - store/
     - repository.py
     - memory_repository.py
     - json_repository.py
     - pg_repository.py
     - dual_repository.py
   - rag/
     - rag_assist.py
     - prompt_builder.py
     - prompt_dsl.py
     - openai_embedder.py
     - openai_llm.py
     - pgvector_retriever.py
 - service/
   - main.py
 - tests/
   - unit/
   - integration/
     - features/demo_qa_healing.feature
     - test_demo_qa_healing_bdd.py
 - prompts/
   - 01_Master_Design_for_xpath_healer.md
   - 02_Prompts Structure.md
   - architecture/
   - phases/
   - tasks/
 - docs/
 - artifacts/

7. Implementation Order

Implementation Phases to Recreate Same Solution

Phase 1 - Project Bootstrap
- Create package skeleton and core domain models (`LocatorSpec`, `CandidateSpec`, `Recovered`, `ElementMeta`).
- Add environment-driven config (`HealerConfig.from_env`).

Phase 2 - Deterministic Core
- Implement strategy registry + strategies + builder.
- Implement validator and retry logic.
- Implement `HealingService` with stage orchestration and tracing.

Phase 3 - Storage
- Implement repository interface + memory/json/postgres/dual repositories.
- Implement schema initialization and CRUD/upsert logic for metadata/events/page index.
- Add operational reset automation:
  - `tools/reset_db_and_chroma.ps1`
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`

Phase 4 - RAG Layer
- Implement embedder/retriever/LLM interfaces and OpenAI/pgvector adapters.
- Implement compact prompt DSL and `RagAssist` with reranking and hallucination guards.

Phase 5 - Facade and API
- Wire everything through `XPathHealerFacade`.
- Expose `/health`, `/generate`, `/heal` via FastAPI.

Phase 6 - Test and Artifacts
- Add unit tests across config/core/store/rag.
- Add Playwright pytest-bdd integration suite with screenshots/video/reports/logs.

8. Constraints

Constraints

- Do not bypass runtime validation before accepting a healed locator.
- Keep deterministic stages available even when adding new model features.
- Keep stage order and stage names stable (used in logs/tests/reports).
- Keep secret values outside source code (`OPENAI_API_KEY`, `XH_PG_DSN`).
- Keep repository contract backward compatible across backends.
- Avoid introducing UI-test-framework specifics into core modules (core must stay library-first).
- Keep DB reset/recreate runbook and script aligned with active schema in `xpath_healer/store/pg_repository.py`.

9. Observability and Logging

Logging Requirements

- Log files:
  - `artifacts/logs/healing-flow.log`
  - `artifacts/logs/integration.log`
- Report artifacts:
  - `artifacts/reports/cucumber.json`
  - `artifacts/reports/integration-junit.xml`
  - `artifacts/reports/healing-calls.jsonl`

Each healing attempt should record:
- `correlation_id`, `app_id`, `page_name`, `element_name`, `field_type`
- stage name and status
- selected locator kind/value
- validation outcome and reason codes
- strategy id
- quality scores: uniqueness/stability/similarity/overall
- retry metadata (`attempts_used`, retry reason)
- RAG telemetry (`raw_context_count`, `prompt_context_count`, `retrieve_k`, `payload_chars`, `embedding_dims`)

10. Future Extensions

Future Capabilities

- Weighted hybrid retrieval (signature vector + lexical + quality prior).
- Multi-model routing and provider abstraction for LLM/embedder.
- Self-healing analytics dashboard (trend by app/page/element/stage).
- Manual review workflow for uncertain model suggestions.
- CI policy packs (strict deterministic-only, hybrid, llm-only A/B experiments).

-----------------------------------------------------------------------------
Regeneration Prompt Contract (copy/paste into an AI coding assistant)
-----------------------------------------------------------------------------

You are recreating XPath Healer exactly as specified by `prompts/01_Master_Design_for_xpath_healer.md`.

Rules:
1. Create the same package structure and module names.
2. Implement deterministic-first staged healing with this order:
   fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag.
3. Keep stage toggles environment-driven via `HealerConfig.from_env`.
4. Use repository abstraction and provide memory/json/postgres/dual implementations.
5. In Postgres schema create: page_index, indexed_elements, elements, locator_variants, quality_metrics, events, healing_events, rag_documents, and pgvector indexes.
6. RAG must be optional and final fallback (except `llm_only` profile), with compact DSL prompt and anti-hallucination filters.
7. Expose FastAPI endpoints `/health`, `/generate`, `/heal`.
8. Add pytest unit tests and pytest-bdd Playwright integration tests with logs/screenshots/video/cucumber+junit reports.
9. Preserve structured logging fields and artifact locations from this design.
10. Do not hardcode secrets; use environment variables only.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

