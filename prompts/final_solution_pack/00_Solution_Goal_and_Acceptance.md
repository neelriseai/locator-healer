Title: XPath Healer Full-Solution Goal and Acceptance

Master architecture alignment:
- Use `prompts/01_Master_Design_for_xpath_healer.md` as the single architecture baseline.

Goal:
1. Build a deterministic-first XPath healer with optional RAG fallback.
2. Keep all layers independently buildable and then integratable.
3. Keep runtime traceability for every healing decision.
4. Keep configuration-driven stage control for experiments and production rollout.

Target layers:
1. Core Healing Layer
2. Database/Storage Layer
3. Service/API Layer
4. Model/RAG Layer
5. Integration and Automation Layer

Global acceptance criteria:
1. Broken locator can be healed using configured stage policy.
2. Deterministic stages run before RAG unless `llm_only` profile is set.
3. Metadata persists in storage and can be reused on later runs.
4. Trace logs and reports clearly show which stage succeeded or failed.
5. Integration scenarios generate screenshots, video, logs, JSON report, and JUnit report.
6. Solution can be recreated on a different machine by following this prompt pack in execution order.

Non-negotiable constraints:
1. No hardcoded secrets.
2. No bypass of validator checks for accepted locator.
3. No stage-name drift from existing flow (`recover_start`, `rag_context`, `rag`, `rag_retry`, `rag_hallucination`, `recover_end`).
4. No dependency on external repository metadata.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

