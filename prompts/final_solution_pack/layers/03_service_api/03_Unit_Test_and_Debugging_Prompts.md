Title: Service API Layer Unit Test and Debugging Prompts

Use this prompt with AI assistant:

Test prompts:

1. Facade initialization tests
- Verify repository wiring for DSN/no-DSN modes.
- Verify RAG adapter initialization guard clauses.

2. API model conversion tests
- Verify `LocatorSpecModel` to/from domain conversion.

3. Endpoint behavior tests
- `/health` returns ok.
- `/generate` returns locator payload.
- `/heal` returns validation errors for missing session context.

Debugging prompts:
1. If `/heal` fails before recovery:
   - inspect session resolver and request validation.
2. If `/heal` returns failed recovery unexpectedly:
   - inspect trace from response and correlated logs.
3. If facade does not initialize RAG:
   - inspect key/DSN/flag availability in current process.

Preferred test commands:
1. `python -m pytest -q tests/unit/test_facade_repository_init.py`
2. `python -m pytest -q tests/unit/test_facade_rag_init.py`

Acceptance criteria:
1. Service remains thin and deterministic.
2. Error responses are explicit and consistent.
3. API payloads remain stable for client integration.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




