Title: Task Prompt - Runbook Validation and Smoke Checklist

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Purpose:
- Provide a repeatable execution checklist to validate full-stack readiness after changes.

Prompt to use with AI assistant:

```
Prepare and execute a runbook validation for XPath Healer aligned with `prompts/01_Master_Design_for_xpath_healer.md`.

Runbook must include:
1. Environment prerequisites (python, playwright browser, postgres, pgvector).
2. Required env vars and safe secret handling.
3. Schema init and DB connectivity checks.
4. Unit test run.
5. Integration test run (pytest-bdd/playwright).
6. Artifact verification checklist.
7. Log verification checklist for stage traces.
8. Common failure triage guide.

Output:
- Exact commands.
- Expected outputs.
- Pass/fail interpretation.
- Follow-up actions for each failure category.
```

Done criteria:
- A new engineer can run the runbook end-to-end and validate system health.
- Runbook reflects current test paths and artifact locations.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

