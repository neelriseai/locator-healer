Title: Task Prompt - Create/Verify Project Structure

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Prompt to use with AI assistant:

```
Verify and align repository structure for XPath Healer using `prompts/01_Master_Design_for_xpath_healer.md`.

Actions:
1. Compare current tree against required structure for:
   - xpath_healer/{api,core,dom,store,rag,utils}
   - service/
   - tests/{unit,integration}
   - prompts/{architecture,phases,tasks}
   - artifacts/{logs,reports,screenshots,videos,metadata}
2. Create missing directories/files only when absent.
3. Add placeholder modules only if needed to complete architecture.
4. Do not modify business logic files in this step.

Output required:
- Missing items list.
- Patch/commands applied.
- Final tree snapshot.
```

Done criteria:
- All architecture folders exist.
- Prompt packs exist for architecture/phases/tasks.
- No unrelated source refactor performed.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

