Title: Task Prompt - Refactor and Review (Safe Mode)

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Prompt to use with AI assistant:

```
Perform a focused refactor/review for XPath Healer while preserving behavior defined in `prompts/01_Master_Design_for_xpath_healer.md`.

Inputs:
- scope_files
- refactor_goal

Review priorities:
1. Behavioral regressions (highest priority).
2. Validation and stage orchestration correctness.
3. Repository and API contract compatibility.
4. Test coverage gaps for modified code.

Refactor rules:
- Keep public method signatures stable unless required.
- Keep stage names/order stable.
- Keep logging contract stable.
- Prefer small, incremental changes.

Required output:
- Findings list ordered by severity with file references.
- Proposed patch summary.
- Regression test plan.
- Residual risk notes.
```

Done criteria:
- Refactor improves readability/maintainability.
- No change in expected runtime behavior unless explicitly requested.
- Tests cover modified branches.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




