Title: Integration and Automation Layer Method and Interface Prompts

Use this prompt with AI assistant:

Key integration method prompts:

1. Settings loader method
- Load defaults from integration config file.
- Override with environment values.
- Produce typed settings object.

2. Artifact directory initialization method
- Ensure required folders exist before run.

3. Logged repository wrapper methods
- Wrap repository `find`, `upsert`, `log_event`, page index methods.
- Emit `hit/miss` and operation status entries.

4. BDD step methods
- Open target page.
- Heal and interact with text-box elements.
- Heal and click explicit checkbox icon.
- Heal and validate web table row values.
- Execute negative raw-xpath path without healer.
- Validate expected trace stages.

5. Report append methods
- Append per-step and per-heal records to JSONL reports.

6. Screenshot and video hooks
- Capture per-step screenshot when enabled.
- Capture final and failure screenshots.
- Save one video per test case.

High-level behavior example:
1. Step calls heal function with broken fallback and hints.
2. Recovered locator is used for action/assertion.
3. Step report and healing-call record are appended.
4. Screenshot is saved for post-run traceability.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

