Prompt Structure and Execution Order

Source of truth precedence:
1. `prompts/01_Master_Design_for_xpath_healer.md`
2. `prompts/final_solution_pack/99_Execution_Order.md`
3. `prompts/final_solution_pack/03_Configuration_Catalog.md`
4. `xpath_healer/core/config.py`, `xpath_healer/api/base.py`, `tests/integration/settings.py`

If any prompt conflicts with code, code wins and prompt must be updated.

Required prompt files (layer-wise)

prompts/
|
|-- architecture/
|   `-- system_design.md
|
|-- phases/
|   |-- configuration_stage_policy.md
|   |-- core_healing.md
|   |-- database_layer.md
|   |-- model_layer.md
|   |-- observability_reporting.md
|   |-- playwright_integration.md
|   |-- selenium_integration.md
|   |-- service_layer.md
|   `-- unit_tests.md
|
|-- tasks/
|   |-- add_tests.md
|   |-- create_structure.md
|   |-- implement_logic.md
|   |-- refactor_review.md
|   `-- runbook_validation.md
|
|-- 01_Master_Design_for_xpath_healer.md
|-- 02_Prompts Structure.md
`-- 03_Layer_Execution_Order.md

Execution mapping (required)

1. Playwright integration:
   - `phases/playwright_integration.md`
   - `tests/integration/test_demo_qa_healing_bdd.py`
   - `adapters/playwright_python/{adapter.py,facade.py}`
2. Selenium integration:
   - `phases/selenium_integration.md`
   - `tests/integration/test_demo_qa_healing_selenium.py`
   - `adapters/selenium_python/{adapter.py,facade.py}`
3. Database/storage:
   - `phases/database_layer.md`
   - `xpath_healer/store/{repository,memory_repository,json_repository,pg_repository,dual_repository}.py`
4. Model/RAG:
   - `phases/model_layer.md`
   - `xpath_healer/rag/{rag_assist,prompt_builder,prompt_dsl,openai_embedder,openai_llm,chroma_retriever}.py`

Authoring rules for all prompt files

1. Keep prompts implementation-first (exact files, exact methods).
2. Preserve runtime stage order exactly:
   `fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag`.
3. Document execution model correctly:
   - stage pipeline sequential
   - selected stage candidate evaluation parallel via `asyncio.gather`
   - selenium adapter thread offload via `asyncio.to_thread`
4. Keep config docs aligned with actual env usage in code.
5. Keep secrets in environment only.
6. Keep retrieval docs Chroma-only (`xh_rag_documents`, `xh_elements`).
7. Include deterministic validation commands.

Operational baseline

1. Run `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1` before end-to-end validation.
2. Keep runbook aligned with `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`.
3. Keep prompt pack entrypoint as `prompts/final_solution_pack/99_Execution_Order.md`.
