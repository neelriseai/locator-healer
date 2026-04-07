Title: Integration and Automation Layer Code Graphs

Layer graph:

BDD Feature
  -> Step Definition
    -> Healer Facade Call
      -> Core + Store + Optional RAG
    -> Action/Assertion on recovered locator
    -> Step report logging
    -> Screenshot capture

Selenium Test
  -> Pytest Function
    -> SeleniumHealerFacade Call
      -> Core + Store + Optional RAG
    -> WebDriver Action/Assertion on recovered locator
    -> Artifact/report logging

Run graph:

Pytest session
  -> settings load
  -> artifact directory setup
  -> browser/page fixtures
  -> scenario execution
  -> screenshots/videos/logs/reports generation

Class/fixture graphs:

1. `IntegrationSettings`
- Holds run-time browser/artifact/capture settings.

2. Logged repository wrapper
- Wraps metadata repository and logs operation status.

3. Scenario state
- Carries recovered locators and traces across step functions.

4. Step functions
- Perform test actions and validations using recovered locators.

5. Selenium test functions
- Perform equivalent scenario actions and validations via WebDriver for parity with Playwright coverage.

Graph usage:
1. Use this graph to reason about where a failure happened:
   setup, heal call, action/assertion, or artifact/report write.
2. Use this graph to maintain test observability while adding new scenarios.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




