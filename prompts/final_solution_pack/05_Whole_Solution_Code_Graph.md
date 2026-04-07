Title: Whole Solution Code Graph

Purpose:
- Visualize end-to-end component flow before implementation.

System graph:

User/Test Step
  -> Integration Layer (pytest-bdd + Playwright)
    -> XPathHealerFacade (api/facade.py)
      -> HealingService (core/healing_service.py)
        -> Stage Orchestration
          -> fallback
          -> metadata (repository read)
          -> rules (strategy builder)
          -> fingerprint
          -> page_index
          -> signature
          -> dom_mining
          -> defaults
          -> position
          -> rag (optional final)
        -> XPathValidator (core/validator.py)
        -> SimilarityService (core/similarity.py)
        -> SignatureExtractor (core/signature.py)
        -> PageIndexer (core/page_index.py)
        -> DomSnapshotter + DomMiner (dom layer)
        -> MetadataRepository (store/repository.py)
          -> InMemoryMetadataRepository
          -> JsonMetadataRepository
          -> PostgresMetadataRepository
          -> DualMetadataRepository
        -> RagAssist (rag/rag_assist.py)
          -> OpenAIEmbedder
          -> ChromaRetriever
          -> OpenAILLM

Persistence graph:

HealingService
  -> repository.upsert(element_meta)
  -> repository.log_event(stage_event)
  -> repository.upsert_page_index(page_index)
  -> repository.find_candidates_by_page(...)
  -> repository.find(...)

Service graph:

FastAPI app (service/main.py)
  -> /health
  -> /generate
    -> facade.generate_locator_async
  -> /heal
    -> page resolver
    -> facade.recover_locator

Artifact graph:

Integration run
  -> artifacts/logs/healing-flow.log
  -> artifacts/logs/integration.log
  -> artifacts/reports/cucumber.json
  -> artifacts/reports/integration-junit.xml
  -> artifacts/reports/healing-calls.jsonl
  -> artifacts/screenshots/*
  -> artifacts/videos/*
  -> artifacts/metadata/*

How to use this graph:
1. Build layer by layer from top to bottom.
2. Keep each arrow contract stable.
3. Add test coverage at each boundary before moving to next layer.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




