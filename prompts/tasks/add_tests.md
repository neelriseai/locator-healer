Title: Task Prompt - Add Tests for a Feature

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Prompt to use with AI assistant:

```
Add tests for a specified feature/module in XPath Healer using architecture and behavior contracts from `prompts/01_Master_Design_for_xpath_healer.md`.

Inputs:
- module_under_test
- test_scope (unit | integration)
- behavior_cases

Requirements:
1. Build a small test plan first (happy path + edge cases + failure path).
2. Use fakes/mocks for external dependencies in unit tests.
3. For integration tests, ensure artifact logging and deterministic assertions.
4. Include assertions for healing trace stages when relevant.
5. Keep tests readable and isolated.

Output:
- New/updated test files.
- Fixtures used.
- Commands to run tests.
- Expected pass/fail interpretation.
```

Done criteria:
- Tests fail before change and pass after change (when applicable).
- Test names reflect behavior.
- No flaky timing/network assumptions in unit tests.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

