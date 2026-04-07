Title: Service API Layer Class Structure Prompt

Use this prompt with AI assistant:

1. Create and validate these classes/components:
   - `XPathHealerFacade`
     - runtime recover entry point
     - authoring generate entry point
     - repository/rag wiring by environment.
   - `LocatorSpecModel` (API model)
     - domain conversion methods.
   - `HealRequest` (API request model)
   - `GenerateRequest` (API request model)
   - `FastAPI app factory` (`create_app`)
     - route registration and dependency wiring.

2. Keep conversion boundary clear:
   - API model <-> domain model conversion in service layer only.

3. Keep facade responsibilities clear:
   - orchestration wiring and high-level use-cases.
   - no direct HTTP concerns inside core.

Acceptance criteria:
1. API and domain models map one-to-one for locator fields.
2. Facade can be reused outside service layer.
3. Service layer remains thin and explicit.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




