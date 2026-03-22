Master Design — XPath Healer (project-tailored)

1. Project Overview

XPath Healer is a layered, deterministic-first framework that repairs broken UI locators during automated tests. It prefers deterministic, rule-based recovery using DOM structure and stored metadata, and falls back to an optional RAG/LLM-assisted stage (embeddings + LLM) when deterministic strategies cannot produce a reliable locator.

2. Core Principles

- Deterministic-first: always attempt rule-based and metadata-driven healing before invoking models.
- Layered and loosely-coupled: core healing, framework integration, storage, service, and model layers are separable and independently testable.
- Testability: every component must support unit tests and replayable integration tests.
- Observability: healing stages emit structured logs and telemetry (failed locator, candidates, ranking, decisions, LLM telemetry).
- Principle of least privilege for secrets: API keys must not be logged; use masked or external secret stores.

3. System Layers

- Core Healing Layer: signature extraction, candidate generation, ranking, validation, and healing decisions (`xpath_healer/core/*`).
- Framework Integration Layer: Playwright/Bdd glue and test interceptors that call the healer (`tests/integration`, BDD features).
- Storage Layer: Dual repository with Postgres primary and JSON fallback (`xpath_healer/store/*`, `PostgresMetadataRepository`, `JsonMetadataRepository`).
- Service Layer: high-level facade (`xpath_healer/api/facade.py`) that wires components and exposes programmatic API.
- Model Layer (optional): embedding + retrieval + LLM assist (`xpath_healer/rag/*` with `OpenAIEmbedder`, `OpenAILLM`, `PgVectorRetriever`, `RagAssist`).

4. High-Level Healing Flow

1. Test action fails with locator-not-found.
2. Framework Integration intercepts the failure and calls the facade.
3. Core extracts a signature (DOM snapshot, attributes) and builds candidates via strategies.
4. Candidates are ranked (similarity, stability, uniqueness) and validated against the live DOM.
5. If a validated candidate is found, it is persisted and returned; test resumes.
6. If deterministic attempts fail and RAG is enabled, the Model Layer composes a prompt, retrieves context via embeddings+PgVectorRetriever, and calls the LLM to propose candidates.
7. LLM candidates are post-processed (dedupe, hallucination checks, grounding) and validated; results are logged with LLM telemetry.

This flow matches existing log stages: `recover_start`, `rag_context`, `rag`, `rag_retry`, `rag_hallucination`, `recover_end`.

5. Module Responsibilities

- `SignatureExtractor` (`core/signature.py`): produce compact DOM signature and token seeds.
- `StrategyRegistry` + strategy modules (`core/strategies`): generate candidate locators (label-based, role, attributes, position, templates).
- `CandidateRanker`/`SimilarityService` (`core/similarity.py`): score candidates by uniqueness/stability/similarity.
- `Validator` (`core/validator.py`): assert candidate correctness against the DOM and business intent.
- `HealingService` (`core/healing_service.py`): orchestrates recovery flow and persistence.
- `RagAssist` (`rag/rag_assist.py`): builds prompt payloads, calls embedder + retriever + LLM, and sanitizes suggestions.
- `OpenAIEmbedder` / `OpenAILLM` (`rag/*`): adapters to OpenAI async client (keep keys out of logs; only record request sizes and response IDs).
- `PostgresMetadataRepository` / `DualMetadataRepository` (`store/*`): storage backends and fallback logic.

6. Project Structure (aligned with repo)

- `xpath_healer/` (source)
  - `core/` — signature, strategies, similarity, validator, healing_service
  - `dom/` — snapshotting and mining
  - `rag/` — embedder, llm adapter, retriever, rag_assist
  - `api/` — `facade.py` wiring
  - `store/` — repositories (Postgres, JSON, in-memory)
  - `utils/`, `store/pg_repository.py` etc.
- `tests/` — `unit/` and `integration/` (BDD features under `tests/integration/features`)
- `docs/` — design docs, prompts
- `artifacts/` — run logs, screenshots, metadata

7. Implementation Order (phased)

Phase 1 — Core stability
- Harden and test `core/*` components and `Validator`.
- Ensure deterministic strategies cover most common cases.

Phase 2 — Tests & Observability
- Add/expand unit tests for core and strategies.
- Standardize structured logs for healing stages and decisions.

Phase 3 — Storage
- Ensure `PostgresMetadataRepository` migrations and `DualMetadataRepository` fallback are stable.

Phase 4 — Framework integration
- Finalize Playwright/Bdd interceptors and integration tests.

Phase 5 — Optional Model/RAG
- Add `OpenAIEmbedder` + `PgVectorRetriever` + `OpenAILLM` + `RagAssist` behind feature flag (`XH_RAG_ENABLED`).
- Add LLM telemetry and safeguards (confidence thresholds, hallucination red flags).

Phase 6 — Service and analytics
- Expose healing API endpoints and build analytics/dashboard features.

8. Constraints

- Phase 1 must not introduce AI/network dependencies.
- Avoid wide-reaching refactors in unrelated modules.
- Do not log secrets (OPENAI_API_KEY); log only masked identifiers or response IDs.
- Keep components cohesive and small; prefer composition over inheritance.

9. Observability and Logging

Logging rules (structured JSON-like fields):
- `correlation_id`, `stage` (recover_start,rag_context,rag,rag_retry,rag_hallucination,recover_end)
- `failed_locator`, `element_name`, `app_id`, `page_name`
- `candidate_locators` (truncated list), `ranking_scores`
- `healing_decision`, `accepted_locator`, `confidence`
- LLM telemetry: `payload_chars`, `embedding_dims`, `prompt_context_count`, `response_id`, `model`, `usage` (token counts)
- Errors and validation failures should include sanitized error codes only.

10. Future Extensions

- Page indexing and full-text/vector search backed by pgvector.
- Pluggable retrievers and LLM adapters (so OpenAI can be swapped for other vendors).
- Healing analytics dashboard and per-app usage reports.
- Fine-grained policy controls for auto-accept vs. manual review of LLM suggestions.

---

Next steps I can take now:
- Commit this doc to the repo (already saved as `docs/Master_Design_for_xpath_healer.md`).
- Create a short checklist to implement Phase 1 changes.
- Add structured log schema enforcement and unit tests.

Which next step would you like me to do?