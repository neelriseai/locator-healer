Title: Phase Prompt - Service Layer (Facade + FastAPI)

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Expose healing and locator generation via API without breaking library-first usage.

Prompt to use with AI assistant:

```
Implement service layer aligned with `prompts/01_Master_Design_for_xpath_healer.md`.

Scope:
- xpath_healer/api/facade.py
- service/main.py

Required API:
1. GET /health
2. POST /generate
3. POST /heal

Service behavior:
- Use `XPathHealerFacade` as orchestration entrypoint.
- Keep request/response models in `service/main.py` via Pydantic.
- `/heal` requires page/session resolver; return structured recovery payload:
  status, correlation_id, strategy_id, trace, locator_spec, updated_meta, error.
- `/generate` returns deterministic locator spec for authoring.

Facade behavior:
- Resolve config from env (`HealerConfig.from_env`).
- Build repositories from env (memory or dual Postgres+JSON).
- Build RAG adapters only when config+key+dsn are valid.

Deliverables:
- API route handlers.
- Domain-model to API-model conversion methods.
- API tests (at least health + generate + heal error paths).
```

Acceptance criteria:
- API is callable with `uvicorn service.main:app --reload`.
- `/health` returns status ok.
- `/generate` returns locator_spec structure.
- `/heal` returns 400 when session_id missing and 503 when resolver unavailable.

Validation commands:
- `python -m pytest -q tests/unit/test_facade_repository_init.py`
- `python -m pytest -q tests/unit/test_facade_rag_init.py`
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

