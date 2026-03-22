Title: Phase Prompt - Configuration and Stage Policy

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Standardize environment-driven execution behavior and profile switching across all layers.

Prompt to use with AI assistant:

```
Implement and document configuration/stage policy for XPath Healer using `prompts/01_Master_Design_for_xpath_healer.md`.

Scope:
- xpath_healer/core/config.py
- .env.example
- README.md
- tests/unit/test_stage_switches.py

Required configuration groups:
1. Stage profile and stage toggles:
   - XH_STAGE_PROFILE
   - XH_STAGE_FALLBACK_ENABLED
   - XH_STAGE_METADATA_ENABLED
   - XH_STAGE_RULES_ENABLED
   - XH_STAGE_FINGERPRINT_ENABLED
   - XH_STAGE_PAGE_INDEX_ENABLED
   - XH_STAGE_SIGNATURE_ENABLED
   - XH_STAGE_DOM_MINING_ENABLED
   - XH_STAGE_DEFAULTS_ENABLED
   - XH_STAGE_POSITION_ENABLED
   - XH_STAGE_RAG_ENABLED
2. RAG settings:
   - XH_RAG_ENABLED, XH_RAG_TOP_K, XH_RAG_PROMPT_TOP_N
   - XH_OPENAI_MODEL, XH_OPENAI_EMBED_MODEL, XH_OPENAI_EMBED_DIM
   - XH_PROMPT_GRAPH_DEEP_DEFAULT, XH_PROMPT_GRAPH_DEEP_RETRY_ENABLED, XH_PROMPT_GRAPH_DEEP_RETRY_MAX
   - XH_LLM_MIN_CONFIDENCE_FOR_ACCEPT
3. Retry settings:
   - XH_RETRY_ENABLED, XH_RETRY_MAX_ATTEMPTS, XH_RETRY_DELAY_MS, XH_RETRY_REASON_CODES
4. Storage settings:
   - XH_PG_DSN, XH_METADATA_JSON_DIR, pooling and schema flags

Required behavior:
- `llm_only` profile disables deterministic stages and keeps rag true.
- Explicit stage flags can override defaults.
- Invalid or missing secrets should disable adapters safely with warnings.
```

Acceptance criteria:
- Config parsing is deterministic.
- Profiles and stage toggles are test-covered.
- `.env.example` and README reflect actual behavior.

Validation commands:
- `python -m pytest -q tests/unit/test_stage_switches.py`
- `python -m pytest -q tests/unit/test_facade_rag_init.py`

