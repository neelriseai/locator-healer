Title: Core Healing Layer Method and Interface Prompts

Use this prompt with AI assistant:

Target methods and plain-English intent:

1. `HealerConfig.from_env`
- Parse all stage and feature flags.
- Support profile override (`full`, `llm_only`).
- Return fully resolved configuration object.

2. `XPathBuilder.build_all_candidates`
- Evaluate registered strategies for allowed stages.
- Return stable ordered candidate list.

3. `StrategyRegistry.register` and `StrategyRegistry.evaluate_all`
- Keep strategy order deterministic.
- Evaluate only strategies that support current field/type context.

4. `XPathValidator.validate_candidate`
- Resolve locator on live page.
- Enforce strictness, visibility, enabled checks, and type gate.
- Return explicit reason codes on fail.

5. `SignatureExtractor.capture`, `build_robust_locator`, `build_robust_xpath`
- Capture stable attributes from matched node.
- Generate robust CSS/XPath candidate from signature.

6. `PageIndexer.build_page_index` and `rank_candidates`
- Parse page DOM into indexed elements.
- Rank candidates against expected profile and context.

7. `FingerprintService.build` and `compare`
- Build weighted token fingerprint.
- Return numeric confidence match for candidate comparison.

8. `SimilarityService.score` and `is_similar`
- Produce similarity score between signatures.
- Enforce threshold behavior.

9. `HealingService.recover_locator`
- Run stage sequence in policy order.
- Evaluate candidate(s) with validator.
- Persist success/failure and stage events.
- Return `Recovered` object with trace.

10. `HealingService._validate_candidate_with_retry`
- Retry only for configured reason codes.
- Keep retry lightweight and bounded.

11. `HealingService._rag_candidates` and `_rag_retry_reason`
- Call RAG only as final stage (unless profile is rag-only).
- Detect red flags and decide deep retry.

12. `LocatorSpec.to_playwright_locator`
- Convert internal locator representation to Playwright calls.

Interface consistency prompt:
1. Keep method input/output models consistent across core methods.
2. Keep reason codes machine-readable and trace-friendly.
3. Keep no side-effect utility methods pure.

High-level behavior example:
1. Fallback fails.
2. Metadata candidate appears and passes validator.
3. Recovery ends without touching deeper stages.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

