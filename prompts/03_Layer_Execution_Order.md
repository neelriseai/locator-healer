Title: Layer Execution Order Prompt

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Purpose:
- Provide strict sequencing so independent contributors can build layers without integration drift.

Prompt to use with AI assistant:

```
Create and follow a delivery plan for XPath Healer aligned to `prompts/01_Master_Design_for_xpath_healer.md`.

Execution sequence:
1. Project structure and config scaffolding.
2. Core deterministic healing engine.
3. Unit tests for core.
4. Playwright integration baseline.
5. Database layer (Postgres + JSON fallback).
6. DB and vector-store operations runbook + automation script (`docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`, `tools/reset_db_and_chroma.ps1`).
7. Service layer (FastAPI + facade wiring).
8. Model layer (RAG/LLM optional fallback).
9. Stage policy and runtime profiles.
10. Observability/reporting and artifacts.
11. Full regression run and hardening.

For each step provide:
- input dependencies
- output deliverables
- blocking risks
- exit criteria
- test commands

Mandatory operational checks:
- Verify PostgreSQL schema/index reset from `tools/reset_db_and_chroma.ps1`.
- Verify Chroma collections (`xh_rag_documents`, `xh_elements`) are recreated.
```

Definition of done:
- Each step has explicit handoff artifacts.
- Later steps do not require redesign of earlier layer contracts.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

