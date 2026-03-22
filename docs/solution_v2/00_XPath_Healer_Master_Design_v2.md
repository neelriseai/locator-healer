# XPath Healer Solution Design v2 (Ordered Layer Architecture)

Date: 2026-03-02
Audience: Core, DB, Service, AI/Model, QA/Automation teams
Version: 2.0

## Architecture Diagram (Start Here)

```text
+----------------------------------------------------------------------------------+
|                              TEST CLIENTS / USERS                               |
|  Playwright BDD | API clients (Postman/cURL) | CI pipelines                      |
+------------------------------------------+---------------------------------------+
                                           |
                                           v
+----------------------------------------------------------------------------------+
|                            FASTAPI SERVICE LAYER                                 |
|  service/main.py + DTO mapping + request validation + correlation logging        |
+------------------------------------------+---------------------------------------+
                                           |
                                           v
+----------------------------------------------------------------------------------+
|                            APPLICATION ORCHESTRATOR                              |
|  XPathHealerFacade -> HealingService -> StrategyRegistry -> Validator            |
+-----------------------+---------------------+--------------------+---------------+
                        |                     |                    |
                        v                     v                    v
              +----------------+    +------------------+   +--------------------+
              | STORE LAYER    |    | DOM/SIGNATURE    |   | OPTIONAL RAG LAYER |
              | (Memory/JSON/  |    | + SIMILARITY     |   | Embedder+Retriever |
              | Postgres)      |    | extraction/scoring|  | + LLM suggestions  |
              +----------------+    +------------------+   +--------------------+
                        |                                           |
                        v                                           |
              +-----------------------+                             |
              | PostgreSQL + pgvector |<----------------------------+
              | elements/events/docs  |
              +-----------------------+
```

## 1) Correct Layer Order (Implementation Sequence)
1. Layer 0: Setup and prerequisites.
2. Layer 1: Core deterministic xpath-healer engine.
3. Layer 2: DB layer (schema + repository + CRUD/events).
4. Layer 3: Service layer (FastAPI API and runtime wiring).
5. Layer 4: Model layer (OpenAI embedder/retriever/LLM + RAG assist).
6. Layer 5: End-to-end testing, regression, performance, release.

Rationale:
- Core contracts are the base.
- DB depends on core models.
- Service depends on core + DB.
- Model/RAG depends on core + DB + service config.
- Full testing is final integration gate.

## 2) Prior Setup Required (All Teams)
- Python 3.11+
- `python -m pip` package management
- Playwright + browser runtime
- pytest + pytest-asyncio + pytest-bdd
- FastAPI + uvicorn
- PostgreSQL 15+
- pgvector enabled
- asyncpg + pgvector python package
- OpenAI SDK (for Layer 4)

## 3) Whole Solution Code Graph

```text
service.main.create_app
  -> xpath_healer.api.facade.XPathHealerFacade
     -> core.context.StrategyContext
     -> core.healing_service.HealingService.recover_locator
        -> core.builder.XPathBuilder.build_all_candidates
           -> core.strategy_registry.StrategyRegistry.evaluate_all
              -> core.strategies.*.build
        -> core.validator.XPathValidator.validate_candidate
        -> core.signature.SignatureExtractor.capture/build_robust_*
        -> core.similarity.SimilarityService.score
        -> store.repository.MetadataRepository (find/upsert/find_candidates/log_event)
           -> store.memory_repository / store.json_repository / store.pg_repository
        -> rag.rag_assist.RagAssist.suggest (optional)
           -> rag.embedder.Embedder
           -> rag.retriever.Retriever
           -> rag.llm.LLM
```

## 4) Public Contract Freeze (Do Not Break)
- `XPathHealerFacade.recover_locator(...) -> Recovered`
- `XPathHealerFacade.generate_locator_async(...) -> LocatorSpec`
- `MetadataRepository.find/upsert/find_candidates_by_page/log_event`
- `LocatorSpec/ElementMeta/Recovered/StrategyTrace` schema fields
- `/health`, `/generate`, `/heal` response envelopes

## 5) Canonical Project Structure

```text
xpath_healer/
  api/facade.py
  core/(models,config,context,builder,strategy_registry,validator,signature,similarity,healing_service,strategies/*)
  store/(repository,memory_repository,json_repository,pg_repository)
  dom/(snapshot,mine)
  rag/(embedder,retriever,llm,rag_assist)
  utils/(text,ids,timing,logging)
service/main.py
tests/unit/*
tests/integration/*
```

## 6) Integration Contracts Between Layers
- Core -> DB: serializes `ElementMeta.to_dict()` and expects lossless `from_dict()` on read.
- Service -> Core: maps JSON request into `LocatorSpec` + vars/hints and returns `Recovered` envelope.
- Core -> Model: sends bounded prompt payload; model returns locator candidates only.
- Model -> Core: candidate suggestions are always re-validated by validator before acceptance.

## 7) Manual Verification Paths
- DB layer: DbVisualizer + SQL query pack (see DB doc).
- Service layer: Postman collection and cURL/PowerShell commands (see Service doc).
- Full suite: pytest unit + integration bdd command pack (see Testing doc).

## 8) Doc Set Produced
- `00_XPath_Healer_Master_Design_v2.docx`
- `01_Core_Layer_Design_v2.docx`
- `02_DB_Layer_Design_v2.docx`
- `03_Service_Layer_Design_v2.docx`
- `04_Model_RAG_Layer_Design_v2.docx`
- `05_Testing_Automation_Layer_Design_v2.docx`

## 9) Prompt Governance
Each layer document includes:
- strict implementation prompt
- file/method checklist
- acceptance criteria
- integration checks

Use prompts layer-by-layer in sequence only.
