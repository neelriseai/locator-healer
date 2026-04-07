Title: Service API Layer Code Graphs

Layer graph:

HTTP request
  -> FastAPI route
    -> request model parse
    -> domain conversion
    -> XPathHealerFacade call
    -> domain response
    -> API response model

Facade graph:

XPathHealerFacade
  -> HealerConfig.from_env
  -> repository initialization
  -> validator/similarity/signature/page-index setup
  -> HealingService
  -> optional RagAssist setup

Class graphs:

1. `LocatorSpecModel`
- Converts API locator payload to `LocatorSpec` domain model and back.

2. `HealRequest`
- Carries runtime recovery input including fallback locator and vars.

3. `GenerateRequest`
- Carries authoring-time generation input.

4. `XPathHealerFacade`
- Central application service for recover/generate/validate calls.

5. `create_app` and route handlers
- HTTP surface around facade methods.

Graph usage:
1. Use this graph when building external service clients.
2. Use this graph to keep service concerns separated from core logic.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




