Title: Global Analysis and Debugging Approach

Purpose:
- Define how to reason, diagnose, and stabilize the solution while building each layer.

Analysis workflow:
1. Reproduce issue with smallest failing scenario.
2. Capture exact stage trace and correlation id.
3. Identify failure stage boundary (input, candidate generation, validation, persistence, or reporting).
4. Confirm expected behavior from master architecture before changing logic.
5. Patch minimally and add targeted tests.

Debugging checkpoints by layer:
1. Core:
   - Verify stage order and stage toggles.
   - Verify candidate list and validator reason codes.
2. Storage:
   - Verify read/write path and fallback behavior.
   - Verify hit/miss patterns and schema compatibility.
3. Model:
   - Verify context payload size and candidate grounding.
   - Verify hallucination flags and retry behavior.
4. Service:
   - Verify request model, response model, and errors for missing session/page.
5. Integration:
   - Verify screenshots/videos/reports and per-step trace logs.

Failure triage map:
1. Locator not found -> inspect fallback and metadata stages.
2. Multiple matches -> inspect validator strictness and hint quality.
3. Stage mismatch in tests -> align assertions with active profile.
4. RAG disabled unexpectedly -> verify API key, DSN, and flags.
5. DB miss for known element -> verify key normalization (`app_id`, `page_name`, `element_name`).

Decision rules:
1. Do not hide failures by weakening validation globally.
2. Prefer deterministic fixes before model-layer tuning.
3. Add observability first when root cause is unclear.
4. Keep performance impact visible when adding retries or deeper context calls.

Quality gate before moving to next layer:
1. Unit tests for changed logic pass.
2. Integration scenario for affected behavior passes or has expected intentional failure.
3. Logs clearly prove why the result is correct.

