Title: Phase Prompt - Configuration and Stage Policy

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Standardize environment-driven runtime behavior and profile switching across core, rag, repository, and integration layers.

Prompt to use with AI assistant:

```
Implement and document configuration/stage policy for XPath Healer.

Scope:
- xpath_healer/core/config.py
- xpath_healer/api/base.py
- tests/integration/settings.py
- tests/integration/conftest.py
- .env.example
- README.md
- tests/unit/test_stage_switches.py

Required configuration groups:

1) Core adapter/stage policy (from HealerConfig.from_env)
- XH_ADAPTER
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

2) Core validator/fingerprint/retry policy
- XH_SIMILARITY_THRESHOLD
- XH_VALIDATOR_REQUIRE_VISIBLE
- XH_VALIDATOR_REQUIRE_ENABLED
- XH_VALIDATOR_STRICT_SINGLE_MATCH
- XH_VALIDATOR_GEOMETRY_ENABLED
- XH_VALIDATOR_GEOMETRY_TOLERANCE
- XH_VALIDATOR_AXIS_ENABLED
- XH_FINGERPRINT_ENABLED
- XH_FINGERPRINT_MIN_SCORE
- XH_FINGERPRINT_ACCEPT_SCORE
- XH_FINGERPRINT_CANDIDATE_LIMIT
- XH_RETRY_ENABLED
- XH_RETRY_MAX_ATTEMPTS
- XH_RETRY_DELAY_MS
- XH_RETRY_REASON_CODES

3) RAG/provider policy
- XH_RAG_ENABLED
- XH_RAG_TOP_K
- XH_RAG_PROMPT_TOP_N
- XH_OPENAI_PROVIDER
- OPENAI_API_KEY
- XH_OPENAI_LLM_API_KEY
- XH_OPENAI_EMBED_API_KEY
- XH_OPENAI_MODEL
- XH_OPENAI_EMBED_MODEL
- XH_OPENAI_EMBED_DIM
- XH_PROMPT_GRAPH_DEEP_DEFAULT
- XH_PROMPT_GRAPH_DEEP_RETRY_ENABLED
- XH_PROMPT_GRAPH_DEEP_RETRY_MAX
- XH_LLM_MIN_CONFIDENCE_FOR_ACCEPT
- XH_AZURE_OPENAI_ENDPOINT
- XH_AZURE_OPENAI_API_VERSION
- XH_AZURE_OPENAI_DEPLOYMENT
- XH_AZURE_OPENAI_CHAT_ENDPOINT
- XH_AZURE_OPENAI_CHAT_API_VERSION
- XH_AZURE_OPENAI_CHAT_DEPLOYMENT
- XH_AZURE_OPENAI_EMBED_ENDPOINT
- XH_AZURE_OPENAI_EMBED_API_VERSION
- XH_AZURE_OPENAI_EMBED_DEPLOYMENT

4) Storage/repository policy
- XH_PG_DSN
- XH_PG_POOL_MIN
- XH_PG_POOL_MAX
- XH_PG_AUTO_INIT_SCHEMA
- XH_METADATA_JSON_DIR
- XH_CHROMA_PATH
- XH_CHROMA_RAG_COLLECTION
- XH_CHROMA_ELEMENTS_COLLECTION
- XH_EMBEDDING_WRITE_ENABLED
- XH_RAG_DOC_MAX_CHARS

5) Integration/runtime execution policy
- XH_BASE_URL
- XH_PLAYWRIGHT_BROWSER
- XH_PLAYWRIGHT_CHANNEL
- XH_PLAYWRIGHT_WINDOW_WIDTH
- XH_PLAYWRIGHT_WINDOW_HEIGHT
- XH_SELENIUM_BROWSER
- XH_SELENIUM_BINARY
- XH_BROWSER_ENGINE
- XH_BROWSER_CHANNEL
- XH_HEADLESS
- XH_ARTIFACTS_ROOT
- XH_REPORTS_DIR
- XH_LOGS_DIR
- XH_SCREENSHOTS_DIR
- XH_VIDEOS_DIR
- XH_METADATA_DIR
- XH_JUNIT_XML
- XH_CUCUMBER_JSON
- XH_STEP_REPORT
- XH_HEALING_CALLS_REPORT
- XH_HTML_REPORT
- XH_SCREENSHOT_EACH_TEST
- XH_SCREENSHOT_ON_FAILURE
- XH_SCREENSHOT_EACH_STEP
- XH_VIDEO_EACH_TEST
- XH_VIDEO_WIDTH
- XH_VIDEO_HEIGHT

Required behavior:
- `llm_only` disables deterministic stages and keeps rag enabled.
- Explicit stage flags can override profile defaults.
- RAG should be disabled safely with warnings when required runtime prerequisites are missing.
- Keep env precedence deterministic: process env overrides `.env.example` defaults.
```

Acceptance criteria:
- Config parsing is deterministic and test-covered.
- Docs and `.env.example` reflect actual env keys used by code.
- No pgvector-only instructions remain in prompts.

Validation commands:
- `python -m pytest -q tests/unit/test_stage_switches.py`
- `python -m pytest -q tests/unit/test_facade_rag_init.py`
