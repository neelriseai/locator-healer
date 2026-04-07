Title: Core Healing Layer Unit Test and Debugging Prompts

Use this prompt with AI assistant:

Unit test prompts by class:

1. `HealingService`
- Verify stage ordering with all stages enabled.
- Verify stage skipping when flags are disabled.
- Verify success path persists metadata and trace.
- Verify fail path returns `all_strategies_failed`.

2. `XPathValidator`
- Verify no-match, multi-match, and exact-match outcomes.
- Verify type gate behavior for textbox/button/checkbox.
- Verify geometry and axis checks when enabled.

3. `StrategyRegistry` and `XPathBuilder`
- Verify ordered strategy execution.
- Verify unsupported strategy is skipped.
- Verify candidate flattening order.

4. `SignatureExtractor`
- Verify robust locator generation from stable attributes.
- Verify XPath generation for missing direct id.

5. `PageIndexer`
- Verify page index extraction from sample DOM.
- Verify candidate ranking returns expected top entry.

6. `FingerprintService` and `SimilarityService`
- Verify scoring boundaries and threshold behavior.

Debugging prompt:
1. For a failed healing run, inspect stage trace first.
2. Identify first failing stage and reason codes.
3. Inspect candidate locator details and validator output.
4. Confirm whether failure is due to strictness, visibility, or ambiguity.
5. Patch smallest responsible function and rerun targeted test.

Preferred test commands:
1. `python -m pytest -q tests/unit/test_healing_service.py`
2. `python -m pytest -q tests/unit/test_validator.py`
3. `python -m pytest -q tests/unit/test_stage_switches.py`
4. `python -m pytest -q tests/unit/test_similarity.py tests/unit/test_fingerprint.py`

Acceptance criteria:
1. Core tests run with no external network dependency.
2. Reason codes are asserted explicitly.
3. Edge cases are covered for retries and strictness.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




