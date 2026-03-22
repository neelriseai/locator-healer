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
          -> PgVectorRetriever
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

