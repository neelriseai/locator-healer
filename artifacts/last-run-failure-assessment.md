# Last Run Failure Assessment

Generated on: 2026-03-08
Run source: `artifacts/reports/integration-junit.xml` (timestamp `2026-03-08T06:30:01.813017+05:30`)

## Suite Summary
- Total tests: 4
- Failures: 4
- Passed: 0
- Metadata backend seen in logs: `DualMetadataRepository(primary=Postgres,fallback=Json)`

---

## 1) test_tc1_textbox_form_fill_and_submit

### Failure reason
- Failed at step: `And trace logs should contain expected healing stages`
- Assertion: `First stage should be fallback for full_name`
- Actual trace starts with `rag`.

### Problem statement to fix
- The test expects a fallback-first cascade, but runtime behavior for this run is RAG-first (or RAG-only), so trace-order assertions fail despite successful element recovery.

### Root cause
- Test assertion in `verify_trace_stages` enforces `trace[0].stage == "fallback"`.
- Latest run traces for `full_name` show only `rag:rag_suggest:ok`.
- Stage configuration is consistent with LLM-only behavior (`.env.example` shows `XH_STAGE_PROFILE=llm_only` and deterministic stages disabled).

### Approach to fix
- Option A (recommended if LLM-only is intended): update trace assertions to accept RAG-first traces.
- Option B (if fallback-first is required): enable fallback/metadata/rules stages and rerun.

### Input given (prompt side)
- From test step inputs (`_heal` call):
  - `app_id=demo-qa-app`
  - `page_name=text_box`
  - `element_name=full_name`
  - `field_type=textbox`
  - `fallback_xpath=//xh-never-match[@id='full_name-broken']`
  - `vars_map={"label":"Full Name","name":"userName","axisHint":"following","strict_single_match":"false"}`

### Vector/RAG details
- Correlation ID: `5add0d104c374ce1a92b47d6632aaeeb`
- `retrieve_k=100`, `top_k=5`, `prompt_top_n=3`
- `embedding_dims=1536`
- `query_chars=463`, `dsl_prompt_chars=1495`, `context_json_chars=1695`, `payload_chars=4144`

### DB-related info
- `find` result: `hit` for `text_box/full_name`
- `upsert` counters after run: `success_count=9`, `fail_count=1`
- Stage events persisted: `recover_start`, `rag_context`, `rag`, `recover_end`

### Context and response observed
- Context stats: `raw_context_count=4`, `prompt_context_count=3`, compression ratio `0.75`
- Model/system response selected:
  - `strategy=rag_suggest`
  - `locator_kind=role`
  - `locator_value=textbox[name='Full Name']`
  - Validation: `ok`, `matched_count=1`, reason `validated`

---

## 2) test_tc2_checkbox_home_icon_select_and_message_verify

### Failure reason
- Failed at step: `And trace logs should contain expected healing stages`
- Assertion: `First stage should be fallback for home_checkbox_icon`
- Actual trace starts with `rag`.

### Problem statement to fix
- Same assertion/config mismatch as TC1: test expects fallback-first trace, but runtime healing trace is RAG-first.

### Root cause
- `verify_trace_stages` requires fallback stage at index 0.
- Latest correlation trace has `rag:rag_suggest:ok` only for the healed element.
- Runtime behavior aligns with LLM-only stage profile.

### Approach to fix
- Option A (recommended if current runtime is intentional): make trace assertions stage-profile aware.
- Option B: enable deterministic stages (`fallback`, `metadata`, `rules`, etc.) before running these assertions.

### Input given (prompt side)
- `app_id=demo-qa-app`
- `page_name=checkbox`
- `element_name=home_checkbox_icon`
- `field_type=checkbox`
- `fallback_xpath=//xh-never-match[@id='home_checkbox_icon-broken']`
- `vars_map={"label":"Home","text":"Home","strict_single_match":"false","target":"icon"}`

### Vector/RAG details
- Correlation ID: `1f0ba35e394f41a18c8a242a56adcc8c`
- `retrieve_k=100`, `top_k=5`, `prompt_top_n=3`
- `embedding_dims=1536`
- `query_chars=446`, `dsl_prompt_chars=1142`, `context_json_chars=630`, `payload_chars=2722`

### DB-related info
- `find` result: `hit` for `checkbox/home_checkbox_icon`
- `upsert` counters: `success_count=8`, `fail_count=2`
- Logged stages: `recover_start`, `rag_context`, `rag`, `recover_end`

### Context and response observed
- Context stats: `raw_context_count=1`, `prompt_context_count=1`, compression ratio `1.0`
- Response selected:
  - `strategy=rag_suggest`
  - `locator_kind=xpath`
  - Locator points to Home label/checkbox icon preceding span
  - Validation: `ok`, `matched_count=1`, reasons `validated_proxy_checkbox, validated`

---

## 3) test_tc3_webtables_first_row_verification

### Failure reason
- Failed in step: `When I heal and verify the first row first name is "Cierra"`
- Assertion from `_heal`: `recovered.status == "success"`
- Actual status: `failed`.

### Problem statement to fix
- Healing for `row1_first_name` must produce a unique locator for first-row first-name cell, but current RAG output is ambiguous and fails validation.

### Root cause
- RAG returned locator `{"kind":"text","value":"Cierra"}` in both light and deep retry passes.
- Validator flagged `multiple_matches` (`matched_count=2`) both times.
- No successful non-RAG stage was executed in this run, so failure had no deterministic fallback path.
- Metadata snapshot shows prior successful locator with disambiguation (`text "Cierra"` + `nth:0`), but it was not used in this run path.

### Approach to fix
- Preferred: re-enable `metadata` stage so prior `last_good` disambiguated locator can be reused.
- Improve RAG output constraints for table cells:
  - include row/column constraints in suggested locator,
  - or require `options.nth=0` when text is not unique,
  - or emit role-based gridcell locator scoped to first row.
- Tighten test input contract to force unique targeting when `allow_position=true` and `occurrence=0` are provided.

### Input given (prompt side)
- `app_id=demo-qa-app`
- `page_name=webtables`
- `element_name=row1_first_name`
- `field_type=text`
- `fallback_xpath=//xh-never-match[@id='row1_first_name-broken']`
- `vars_map={"text":"Cierra","match_mode":"exact","occurrence":"0","allow_position":"true","strict_single_match":"false"}`

### Vector/RAG details
- Correlation ID: `bc48bc49b9cb49dab9ea26f21af44bf0`
- Light pass: `retrieve_k=100`, `top_k=5`, `prompt_top_n=3`, `embedding_dims=1536`
- Deep retry pass (`deep_1`) executed after `rag_retry`.
- Both passes used same context sizing (`raw_context_count=2`, `prompt_context_count=2`, compression `1.0`).

### DB-related info
- `find` result: `hit` for `webtables/row1_first_name`
- `upsert` counters: `success_count=4`, `fail_count=5`
- Logged stages include `rag_retry` and `rag_hallucination` with reason `validator_red_flags`.

### Context and response observed
- Context stats: `query_chars=443`, `dsl_prompt_chars=930`, `context_json_chars=601`, `payload_chars=2476`
- Response (light):
  - locator `text=Cierra`, score `0.8`, validation failed `multiple_matches (2)`
  - LLM reason: top reranked candidate, but ambiguity not resolved
- Response (deep_1 retry):
  - locator `text=Cierra`, score `0.85`, same validation failure
  - Final: `recover_end=fail`, error `All healing stages failed to produce a valid locator.`

---

## 4) test_tc4_raw_fallback_xpath_fails_without_healer

### Failure reason
- Failure is intentional by test design.
- `pytest.fail("Intentional failure: raw fallback xpath did not resolve any element...")` is called in step `report and logs should show xpath failure reason`.

### Problem statement to fix
- If CI pipeline expects a green run, this negative test should not hard-fail the suite.

### Root cause
- Step implementation explicitly fails after verifying expected negative condition (`matched_count == 0`).

### Approach to fix
- Keep as-is if you intentionally require a red test for demonstration.
- Otherwise:
  - replace `pytest.fail(...)` with assertions/log-only checks, or
  - mark scenario as expected failure (`xfail`) and separate it from pass-gating runs.

### Input given (prompt/vector/db/context)
- No healing prompt/LLM/vector flow for this step (healer not invoked).
- Raw input used: `//xh-never-match[@id='raw_xpath_negative-broken']`

### DB-related info
- No healing DB stage flow for this case.
- One report record appended with:
  - `status=failed_without_healer`
  - `reason=raw_xpath_no_match`
  - `matched_count=0`

### Response observed
- Raw xpath lookup returned `0` matches and logged `raw_xpath_lookup_failed`.
- Test then failed intentionally.

---

## Cross-Test Observations
- TC1 and TC2 are functional successes in healing but test failures in trace expectation logic.
- TC3 is a real healing failure due to ambiguous locator resolution.
- TC4 is an intentional negative failure.
- For this run, stage events are RAG-centric (`recover_start -> rag_context -> rag -> recover_end`), with no fallback stage entries for failing TC1/TC2 trace checks.
