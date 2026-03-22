Title: Core Healing Layer Architecture Prompt

Layer objective:
- Build deterministic healing orchestration and validation engine.

Use this prompt with AI assistant:

1. Implement the Core Healing Layer exactly aligned to the master architecture.
2. Keep stage sequence:
   fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag.
3. Keep stage execution configurable from environment.
4. Ensure every candidate is validated before acceptance.
5. Ensure success and failure are both persisted with structured trace.
6. Ensure scoring metrics are captured (uniqueness, stability, similarity, overall).
7. Keep deterministic behavior available even when RAG is enabled.

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

Acceptance criteria:
1. Healing attempt always has correlation id and stage traces.
2. Stage toggles can disable/enable layers without code changes.
3. Validator blocks invalid candidate.
4. Successful healing returns locator + updated metadata.
5. Failed healing returns reason and full trace.

