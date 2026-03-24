Title: Service API Layer Architecture Prompt

Layer objective:
- Expose healer capabilities over HTTP while keeping library-first architecture.

Use this prompt with AI assistant:

1. Build a thin API wrapper around existing facade orchestration.
2. Keep endpoints minimal and explicit:
   - `/health`
   - `/generate`
   - `/heal`
3. Keep request/response models stable and aligned with core domain models.
4. Keep page/session resolver injectable for runtime automation sessions.
5. Keep error handling explicit with correct status codes.

Primary files:
1. `service/main.py`
2. `xpath_healer/api/facade.py`

Acceptance criteria:
1. Service can run standalone with Uvicorn.
2. `/generate` works without browser session.
3. `/heal` validates required session/page context before recover call.
4. Response includes trace and error details when healing fails.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

