Title: Core Healing Layer Architecture Prompt

Layer objective:
- Build deterministic healing orchestration and validator-gated acceptance exactly matching current runtime behavior.

Mandatory reference:
- `prompts/final_solution_pack/08_Algorithm_Inventory.md` (sections 1, 2, 3, 4)

Use this prompt with AI assistant:

1. Implement core stage cascade with exact order:
   fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag
2. Preserve stage-policy behavior:
   - profile + per-stage toggles from `HealerConfig.from_env`
   - `llm_only` disables deterministic stages and keeps rag on
3. Preserve execution model:
   - stage pipeline sequential
   - parallel candidate evaluation only where `_evaluate_candidates_parallel` is used
4. Keep retry behavior configurable (`XH_RETRY_*`) and reason-code gated.
5. Ensure every accepted candidate passes validator gates.
6. Persist success/failure with trace and quality metrics.

Required formulas/contracts to preserve:
1. Metadata stage fixed strategy scores (`metadata.last_good`, `metadata.robust*`, `metadata.live*`).
2. Signature + graph context scoring:
   - combined_score = 0.70 * similarity + 0.30 * graph_context
   - effective_score = max(similarity, combined_score)
3. Graph-context weighting:
   - 0.25*tag + 0.30*container + 0.25*anchor + 0.10*text + 0.10*field_type_compat
4. Similarity formula:
   - 0.55*attrs + 0.20*text + 0.15*tag + 0.10*container - volatility_penalty
5. Page index ranking weights and fingerprint weights from inventory.
6. Post-success quality metric formula:
   - overall = 0.4*uniqueness + 0.4*stability + 0.2*similarity(if present)

Primary files to target:
1. `xpath_healer/core/healing_service.py`
2. `xpath_healer/core/validator.py`
3. `xpath_healer/core/builder.py`
4. `xpath_healer/core/strategy_registry.py`
5. `xpath_healer/core/signature.py`
6. `xpath_healer/core/fingerprint.py`
7. `xpath_healer/core/similarity.py`
8. `xpath_healer/core/page_index.py`
9. `xpath_healer/core/config.py`
10. `xpath_healer/core/models.py`
11. `xpath_healer/api/base.py`

Acceptance criteria:
1. Healing attempt always has correlation id and stage traces.
2. Stage toggles can disable/enable layers without code changes.
3. Validator blocks invalid candidates.
4. Successful healing returns locator + updated metadata.
5. Failed healing returns reason and full trace.
