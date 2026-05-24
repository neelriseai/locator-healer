Title: Task Prompt - Implement Logic Change Safely

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Prompt to use with AI assistant:

```
Implement a focused logic change in XPath Healer while preserving architecture contracts from `prompts/01_Master_Design_for_xpath_healer.md`.

Inputs:
- task_description: <what to change>
- target_files: <exact files>
- expected_behavior: <observable result>

Required workflow:
1. Read target files and dependent modules.
2. Propose minimal patch scope.
3. Implement only required code paths.
4. Add or update tests for changed behavior.
5. Run relevant unit/integration checks.
6. Provide summary with risk notes.

Rules:
- Keep stage order unchanged unless explicitly requested.
- Do not bypass validator for accepted locators.
- Do not hardcode env secrets.
- Keep backward-compatible public models where possible.

Output:
- Files changed.
- What behavior changed.
- Test evidence.
```

Done criteria:
- Behavior matches expected output.
- Tests for new/changed path are present and passing.
- No unrelated module modifications.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




