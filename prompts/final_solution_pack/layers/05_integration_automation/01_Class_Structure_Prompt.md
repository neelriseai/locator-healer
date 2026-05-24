Title: Integration and Automation Layer Class Structure Prompt

Use this prompt with AI assistant:

1. Create and maintain these integration structures:
   - `IntegrationSettings` dataclass
   - browser/page/session fixtures for Playwright and Selenium
   - scenario-state container for step communication
   - optional logged repository wrapper for DB operation visibility
   - adapter-specific facades (`XPathHealerFacade`, `SeleniumHealerFacade`)

2. Keep clear concerns:
   - settings loader handles environment + config file merge.
   - conftest handles runtime fixtures and artifact lifecycle.
   - Playwright BDD step file handles scenario behavior.
   - Selenium integration file handles direct pytest scenarios.

3. Keep artifact paths centralized:
   - logs
   - reports
   - screenshots
   - videos
   - metadata

Acceptance criteria:
1. Test setup is configurable without changing step logic.
2. Artifact behavior is controlled by integration settings flags.
3. DB operation logs can be correlated with healing traces.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




