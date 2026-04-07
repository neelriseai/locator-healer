Title: Core Healing Layer Method and Interface Prompts

Mandatory reference:
- `prompts/final_solution_pack/08_Algorithm_Inventory.md` (sections 1, 2, 3, 4)

Use this prompt with AI assistant:

Target methods and intent:

1. `HealerConfig.from_env`
- Parse all stage and feature flags.
- Support profile override (`full`, `llm_only`).
- Parse retry/fingerprint/validator prompts exactly.

2. `XPathBuilder.build_all_candidates`
- Evaluate registered strategies for allowed stages.
- Keep deterministic ordering via strategy priority.

3. `StrategyRegistry.register` and `StrategyRegistry.evaluate_all`
- Preserve registered priority order.
- Respect stage/field context filtering.

4. `XPathValidator.validate_candidate`
- Resolve locator on live page.
- Enforce strictness, visibility, enabled checks, and field-type gates.
- Return explicit reason codes on fail.

5. `SignatureExtractor.capture`, `build_robust_locator`, `build_robust_xpath`
- Capture stable attributes from matched node.
- Generate robust CSS/XPath candidate from signature.

6. `PageIndexer.build_page_index` and `rank_candidates`
- Parse page DOM into indexed elements.
- Rank candidates with configured weighted formula from inventory.

7. `FingerprintService.build` and `compare`
- Build weighted token fingerprint.
- Preserve exact weighting contract and hash short-circuit behavior.

8. `SimilarityService.score` and `is_similar`
- Preserve weighted similarity formula from inventory.
- Enforce threshold behavior.

9. `HealingService.recover_locator`
- Run exact stage sequence.
- Preserve sequential orchestration + selected stage parallel evaluation.
- Persist success/failure and emit stage events.

10. `HealingService._validate_candidate_with_retry`
- Retry only for configured reason codes.
- Preserve bounded retry semantics.

11. `HealingService._rag_candidates` and `_rag_retry_reason`
- Call RAG only as final stage (unless profile settings dictate).
- Preserve reason-based deep retry trigger behavior.

12. Quality metric methods in `HealingService`
- Preserve formulas for uniqueness/stability/similarity/overall scoring.

Interface consistency constraints:
1. Keep method input/output models stable.
2. Keep reason codes machine-readable and trace-friendly.
3. Keep utility methods deterministic and side-effect safe.

High-level behavior example:
1. Fallback fails.
2. Metadata candidates are evaluated.
3. Best valid candidate is selected and persisted.
4. Deeper stages are skipped after success.
