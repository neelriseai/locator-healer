Prompt Structure and Execution Order

Source of truth:
- Always align every prompt with `prompts/01_Master_Design_for_xpath_healer.md`.
- If any prompt conflicts with master design, master design wins.

Required prompt files (layer-wise)

prompts/
|
|-- architecture/
|   |-- system_design.md
|
|-- phases/
|   |-- core_healing.md
|   |-- unit_tests.md
|   |-- playwright_integration.md
|   |-- database_layer.md
|   |-- service_layer.md
|   `-- model_layer.md
|
`-- tasks/
    |-- create_structure.md
    |-- implement_logic.md
    |-- add_tests.md
    `-- refactor_review.md

Additional prompt files required for this project

prompts/
|
|-- 03_Layer_Execution_Order.md
|
|-- phases/
|   |-- configuration_stage_policy.md
|   `-- observability_reporting.md
|
`-- tasks/
    `-- runbook_validation.md

Operational docs/scripts required for reproducible setup

- `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- `tools/reset_db_and_chroma.ps1`

Execution order

1. `tasks/create_structure.md`
2. `phases/core_healing.md`
3. `phases/unit_tests.md`
4. `phases/playwright_integration.md`
5. `phases/database_layer.md`
6. `phases/service_layer.md`
7. `phases/model_layer.md`
8. `phases/configuration_stage_policy.md`
9. `phases/observability_reporting.md`
10. `tasks/add_tests.md`
11. `tasks/refactor_review.md`
12. `tasks/runbook_validation.md`

Authoring rules for all prompt files

1. Keep prompts implementation-oriented, not generic theory.
2. Include exact module and method names from current repo.
3. Include acceptance criteria and "done" checks.
4. Include commands for validation (`python -m pytest ...`).
5. Include constraints to prevent unrelated refactors.
6. Keep secrets in env vars only (`OPENAI_API_KEY`, `XH_PG_DSN`).
7. Preserve stage names and order used by healing traces.
8. Include DB reset/recreate validation using:
   - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
9. Keep prompts aligned with Chroma-backed retrieval (`xh_rag_documents`, `xh_elements`).

Detailed execution pack generated:
- `prompts/final_solution_pack/`
- Start with `prompts/final_solution_pack/99_Execution_Order.md`
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

