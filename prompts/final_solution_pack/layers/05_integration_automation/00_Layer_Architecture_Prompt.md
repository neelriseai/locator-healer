Title: Integration and Automation Layer Architecture Prompt

Layer objective:
- Validate full healing behavior in browser-driven BDD scenarios with auditable artifacts.

Use this prompt with AI assistant:

1. Build integration layer using pytest-bdd and Playwright.
2. Define scenarios with intentionally broken fallback locators.
3. Call healer facade during runtime step actions.
4. Validate business outcomes and healing stage traces.
5. Capture artifact evidence per step and per test.

Primary files:
1. `tests/integration/features/demo_qa_healing.feature`
2. `tests/integration/test_demo_qa_healing_bdd.py`
3. `tests/integration/conftest.py`
4. `tests/integration/settings.py`
5. `tests/integration/config.json`

Acceptance criteria:
1. Scenarios execute in configured browser mode.
2. Healing traces are available for each healed element.
3. Reports and media artifacts are generated for investigation.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

