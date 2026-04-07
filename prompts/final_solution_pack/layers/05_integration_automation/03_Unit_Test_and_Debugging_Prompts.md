Title: Integration and Automation Layer Test and Debugging Prompts

Use this prompt with AI assistant:

Integration test prompts:
1. Positive scenario: text box fill, submit, output verify.
2. Positive scenario: checkbox icon click and message verify.
3. Positive scenario: web table row first/last name verify through healed locators.
4. Negative scenario: raw invalid fallback xpath without healer must fail and log reason.
5. Selenium scenario parity: run same business checks through `test_demo_qa_healing_selenium.py`.

Verification prompts:
1. Verify trace contains expected stage path for each healed element.
2. Verify reports contain selected locator and strategy details.
3. Verify one video file per test case.
4. Verify screenshots exist per step and on failures.

Debugging prompts:
1. If stage assertions fail:
   - verify current stage profile in environment.
2. If integration scenario fails intermittently:
   - inspect screenshot timeline and `integration.log`.
3. If DB hit/miss behavior is inconsistent:
   - compare requested key tuple with stored metadata keys.
4. If RAG behavior is unclear:
   - inspect `healing-flow.log` for `rag_context`, `rag`, `rag_retry`, `rag_hallucination`.

Preferred execution command:
1. `python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json`
2. `python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_selenium.py --cucumberjson=artifacts/reports/cucumber-selenium.json --junitxml=artifacts/reports/integration-selenium-junit.xml`

Acceptance criteria:
1. Integration suite provides deterministic evidence of behavior.
2. Negative test remains intentionally failing and clearly reported.
3. Artifacts are sufficient for root-cause debugging.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




