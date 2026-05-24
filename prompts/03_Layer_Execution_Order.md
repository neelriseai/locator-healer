Title: Layer Execution Order Prompt

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Purpose:
- Provide strict sequencing so contributors can build and verify layers without contract drift.

Prompt to use with AI assistant:

```
Create and follow a delivery plan for XPath Healer aligned to `prompts/01_Master_Design_for_xpath_healer.md`.

Build sequence:
1. Project structure and env/config scaffolding.
2. Core deterministic healing engine.
3. Unit tests for core and config switches.
4. Database/storage layer (Postgres + JSON fallback + Chroma collection wiring).
5. Service layer (FastAPI + facade wiring).
6. Model layer (RAG/LLM optional fallback).
7. Playwright integration baseline.
8. Selenium integration baseline.
9. Observability/reporting and artifact validation.
10. Full regression run and hardening.

Runtime execution model that must be documented and preserved:
1. Stage order:
   fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag
2. Stage flow is sequential.
3. Candidate evaluation is parallel (asyncio.gather) for metadata/rules/fingerprint/page_index/defaults.
4. Candidate evaluation is sequential for fallback/signature/dom_mining/position/rag.
5. Selenium runtime adapter uses asyncio.to_thread for blocking webdriver operations.
6. Playwright runtime adapter is async-native.

Required file mapping:
- Playwright integration test: `tests/integration/test_demo_qa_healing_bdd.py`
- Selenium integration test: `tests/integration/test_demo_qa_healing_selenium.py`
- Playwright adapter: `adapters/playwright_python/{adapter.py,facade.py}`
- Selenium adapter: `adapters/selenium_python/{adapter.py,facade.py}`
- Core orchestrator: `xpath_healer/core/healing_service.py`
- Config parser: `xpath_healer/core/config.py`
- RAG env/runtime wiring: `xpath_healer/api/base.py`
- RAG retriever: `xpath_healer/rag/chroma_retriever.py`

For each build step provide:
- input dependencies
- output deliverables
- blocking risks
- exit criteria
- validation commands

Mandatory operational checks:
- Verify PostgreSQL schema/index reset from `tools/reset_db_and_chroma.ps1`.
- Verify Chroma collections (`xh_rag_documents`, `xh_elements`) are recreated.
```

Definition of done:
- Each step has explicit handoff artifacts.
- Later steps do not require redesign of earlier layer contracts.
- Config/env matrix stays aligned with `prompts/final_solution_pack/03_Configuration_Catalog.md`.
