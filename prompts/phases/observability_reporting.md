Title: Phase Prompt - Observability, Reporting, and Artifacts

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Ensure healing decisions are traceable from logs, reports, screenshots, and videos.

Prompt to use with AI assistant:

```
Implement observability and reporting for XPath Healer aligned with `prompts/01_Master_Design_for_xpath_healer.md`.

Scope:
- xpath_healer/utils/logging.py
- tests/integration/conftest.py
- tests/integration/test_demo_qa_healing_bdd.py
- any report writer utilities used by integration layer

Required outputs:
1. Structured stage logs with fields:
   correlation_id, app_id, page_name, element_name, field_type, stage, status, score, details
2. Healing call report entries with:
   fallback locator, selected locator, strategy_id, quality metrics, trace list
3. Integration artifacts:
   - cucumber.json
   - junit xml
   - integration.log
   - healing-flow.log
   - screenshots per step + failures
   - one video per test case

Behavior requirements:
- Ensure stage traces reflect active policy (deterministic or rag).
- Ensure failure reasons are explicit (e.g., no_match, multiple_matches, validation_failed).
- Ensure DB operation logs include hit/miss status where applicable.
```

Acceptance criteria:
- Artifact files are produced on integration run.
- Logs can prove which layer handled each healing.
- Reports contain healed locator details and trace path.

Validation command:
- `python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json`
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




