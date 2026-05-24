Title: Phase Definitions (A to G)

Purpose:
- Define what each phase means so an AI assistant can map tasks correctly before implementation.

Phase A: Global preparation
1. Establish goals, dependencies, environment, configuration, schema, and debugging approach.
2. Output is readiness to start coding with clear constraints and setup.

Phase B: Core layer
1. Build deterministic healing engine and its unit test baseline.
2. Output is working core orchestration with validator and stage policy.

Phase C: Database layer
1. Build storage contract implementations and schema-backed persistence.
2. Output is stable metadata/event/page-index persistence with fallback behavior.

Phase D: Service layer
1. Build facade wiring and HTTP service endpoints.
2. Output is callable API that exposes generate/heal use cases.

Phase E: Model layer
1. Build optional RAG/LLM adapters and orchestration safeguards.
2. Output is validator-gated model fallback with telemetry.

Phase F: Integration layer
1. Build pytest-bdd + Playwright automation and Selenium automation, both with reporting artifacts.
2. Output is executable end-to-end scenarios with healing traces and media evidence.

Phase G: End-to-end validation
1. Run complete verification across enabled layers.
2. Output is final confidence baseline and frozen run configuration.

Fast-track mapping:
1. Core + automation-only path = Phase A -> Phase B -> Phase F -> selective Phase G.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




