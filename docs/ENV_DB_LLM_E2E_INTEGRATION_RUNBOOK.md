# XPath Healer End-to-End Setup, Layer Flow, and Test Runbook

This document is a single operational reference for:
- environment setup (OpenAI, DB, browser, screenshots, video, stage/retry switches),
- unit/integration test commands,
- BDD invalid XPath injection points and heal call points,
- end-to-end layer integration flow (framework -> facade -> core -> store -> model/LLM),
- where DB methods, prompt creation, LLM calls, and retry logic run,
- unit test coverage by layer.

## 1) Environment Setup Commands (PowerShell)

### 1.1 Current session setup (recommended for local test runs)

```powershell
# Core adapter + target app
$env:XH_ADAPTER='playwright_python'                       # or selenium_python
$env:XH_BASE_URL='https://demo-qa-app.azurewebsites.net'

# OpenAI + DB
$env:OPENAI_API_KEY='YOUR_OPENAI_KEY'
$env:XH_PG_DSN='postgresql://postgres:YOUR_PASSWORD@localhost:5432/postgres'
$env:XH_PG_POOL_MIN='1'
$env:XH_PG_POOL_MAX='10'
$env:XH_PG_AUTO_INIT_SCHEMA='true'

# Chroma + metadata
$env:XH_CHROMA_PATH='artifacts/chroma'
$env:XH_CHROMA_RAG_COLLECTION='xh_rag_documents'
$env:XH_CHROMA_ELEMENTS_COLLECTION='xh_elements'
$env:XH_METADATA_JSON_DIR='artifacts/metadata'
$env:XH_EMBEDDING_WRITE_ENABLED='true'
$env:XH_RAG_DOC_MAX_CHARS='1400'

# RAG + model
$env:XH_RAG_ENABLED='true'
$env:XH_RAG_TOP_K='5'
$env:XH_RAG_PROMPT_TOP_N='3'
$env:XH_OPENAI_MODEL='gpt-4.1'
$env:XH_OPENAI_EMBED_MODEL='text-embedding-3-large'
$env:XH_OPENAI_EMBED_DIM='1536'
$env:XH_LLM_MIN_CONFIDENCE_FOR_ACCEPT='0.65'

# Prompt deep-graph retry controls (RAG retry)
$env:XH_PROMPT_GRAPH_DEEP_DEFAULT='true'
$env:XH_PROMPT_GRAPH_DEEP_RETRY_ENABLED='true'
$env:XH_PROMPT_GRAPH_DEEP_RETRY_MAX='1'

# Stage profile + per-stage toggles
$env:XH_STAGE_PROFILE='full'                              # use llm_only for model-only mode
$env:XH_STAGE_FALLBACK_ENABLED='true'
$env:XH_STAGE_METADATA_ENABLED='true'
$env:XH_STAGE_RULES_ENABLED='true'
$env:XH_STAGE_FINGERPRINT_ENABLED='true'
$env:XH_STAGE_PAGE_INDEX_ENABLED='true'
$env:XH_STAGE_SIGNATURE_ENABLED='true'
$env:XH_STAGE_DOM_MINING_ENABLED='true'
$env:XH_STAGE_DEFAULTS_ENABLED='true'
$env:XH_STAGE_POSITION_ENABLED='true'
$env:XH_STAGE_RAG_ENABLED='true'

# Fingerprint controls
$env:XH_FINGERPRINT_ENABLED='true'
$env:XH_FINGERPRINT_MIN_SCORE='0.75'
$env:XH_FINGERPRINT_ACCEPT_SCORE='0.90'
$env:XH_FINGERPRINT_CANDIDATE_LIMIT='25'

# Validation retry controls (candidate retry)
$env:XH_RETRY_ENABLED='true'
$env:XH_RETRY_MAX_ATTEMPTS='2'
$env:XH_RETRY_DELAY_MS='30'
$env:XH_RETRY_REASON_CODES='locator_error,locator_timeout,stale_element,not_visible'

# Browser selection
$env:XH_HEADLESS='true'
$env:XH_PLAYWRIGHT_BROWSER='chromium'                     # chromium|chrome|edge|firefox|webkit
$env:XH_PLAYWRIGHT_CHANNEL=''                             # optional: chrome|msedge|...
$env:XH_SELENIUM_BROWSER='chrome'                         # chrome|chromium|edge|firefox
$env:XH_SELENIUM_BINARY=''                                # optional binary path

# Artifacts + report paths
$env:XH_ARTIFACTS_ROOT='artifacts'
$env:XH_REPORTS_DIR='artifacts/reports'
$env:XH_LOGS_DIR='artifacts/logs'
$env:XH_SCREENSHOTS_DIR='artifacts/screenshots'
$env:XH_VIDEOS_DIR='artifacts/videos'
$env:XH_METADATA_DIR='artifacts/metadata'
$env:XH_JUNIT_XML='artifacts/reports/integration-junit.xml'
$env:XH_CUCUMBER_JSON='artifacts/reports/cucumber.json'
$env:XH_STEP_REPORT='artifacts/reports/steps.jsonl'
$env:XH_HEALING_CALLS_REPORT='artifacts/reports/healing-calls.jsonl'
$env:XH_HTML_REPORT='artifacts/reports/integration-report.html'

# Capture switches
$env:XH_SCREENSHOT_EACH_TEST='true'
$env:XH_SCREENSHOT_ON_FAILURE='true'
$env:XH_SCREENSHOT_EACH_STEP='true'
$env:XH_VIDEO_EACH_TEST='true'
$env:XH_VIDEO_WIDTH='640'
$env:XH_VIDEO_HEIGHT='360'
```

### 1.2 LLM-only profile quick switch

```powershell
$env:XH_STAGE_PROFILE='llm_only'
$env:XH_RAG_ENABLED='true'
$env:XH_STAGE_RAG_ENABLED='true'

$env:XH_STAGE_FALLBACK_ENABLED='false'
$env:XH_STAGE_METADATA_ENABLED='false'
$env:XH_STAGE_RULES_ENABLED='false'
$env:XH_STAGE_FINGERPRINT_ENABLED='false'
$env:XH_STAGE_PAGE_INDEX_ENABLED='false'
$env:XH_STAGE_SIGNATURE_ENABLED='false'
$env:XH_STAGE_DOM_MINING_ENABLED='false'
$env:XH_STAGE_DEFAULTS_ENABLED='false'
$env:XH_STAGE_POSITION_ENABLED='false'
$env:XH_FINGERPRINT_ENABLED='false'
```

### 1.3 Persistent key/DSN (user scope)

```powershell
setx OPENAI_API_KEY "YOUR_OPENAI_KEY"
setx XH_PG_DSN "postgresql://postgres:YOUR_PASSWORD@localhost:5432/postgres"
setx XH_OPENAI_MODEL "gpt-4.1"
setx XH_OPENAI_EMBED_MODEL "text-embedding-3-large"
```

Notes:
- `.env` and `.env.example` are auto-loaded by `load_env_into_process(...)` in integration setup and settings loading:
  - `xpath_healer/utils/env.py`
  - `tests/integration/conftest.py`
  - `tests/integration/settings.py`

## 2) Test Commands

### 2.1 Install

```powershell
python -m pip install -e .[dev,similarity,dom,db,llm]
```

### 2.2 Unit tests

```powershell
python -m pytest -q tests\unit
```

### 2.3 Integration tests (Playwright BDD)

Only pass scenarios (exclude intentional negative):
```powershell
python -m pytest -q -rs -m "integration and not negative" tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json
```

Include all scenarios (includes intentional failure TC4):
```powershell
python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json
```

### 2.4 Integration tests (Selenium)

```powershell
python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_selenium.py --junitxml=artifacts/reports/integration-junit.xml
```

### 2.5 Full test discovery behavior

- Pytest test root and markers are configured in `pyproject.toml`:
  - `[tool.pytest.ini_options]` at `pyproject.toml:35`
  - `testpaths = ["tests"]` at `pyproject.toml:37`
  - `integration` marker at `pyproject.toml:40`

## 3) BDD Test and Invalid XPath Injection Points

- Feature file:
  - `tests/integration/features/demo_qa_healing.feature`
- BDD step bindings:
  - `tests/integration/test_demo_qa_healing_bdd.py:29` (`scenarios(...)`)

Invalid XPath is intentionally created here:
- `_broken_fallback(...)`:
  - `tests/integration/test_demo_qa_healing_bdd.py:112`
  - Returns `//xh-never-match[@id='{name}-broken']`

Heal call entry in BDD flow:
- `_heal(...)`:
  - `tests/integration/test_demo_qa_healing_bdd.py:116`
- Actual call to healer:
  - `healer.recover_locator(...)` at `tests/integration/test_demo_qa_healing_bdd.py:130`

Raw negative path without healer:
- `query_raw_invalid_fallback_without_healer(...)`:
  - `tests/integration/test_demo_qa_healing_bdd.py:502`
- Intentional fail for reporting:
  - `pytest.fail(...)` at `tests/integration/test_demo_qa_healing_bdd.py:538`

## 4) Layer-by-Layer Design and Capabilities

### 4.1 Integration Automation Layer

Main files:
- `tests/integration/settings.py:47` `load_settings(...)`
- `tests/integration/conftest.py:402` `metadata_repository(...)`
- `tests/integration/conftest.py:452` `page(...)`
- `tests/integration/conftest.py:537` `pytest_bdd_after_step(...)`
- `tests/integration/conftest.py:579` `pytest_bdd_step_error(...)`
- `tests/integration/conftest.py:629` `pytest_sessionfinish(...)`

Capabilities:
- Browser launch selection (Playwright/Selenium options from env/config).
- Per-step/per-test screenshots and per-test video capture.
- DB operation logging wrappers via `LoggedMetadataRepository`.
- JSONL and HTML report generation.

### 4.2 API/Facade Layer

Main files:
- `xpath_healer/api/factory.py:24` `create_healer_facade(...)`
- `xpath_healer/api/base.py:43` `BaseHealerFacade`
- `xpath_healer/api/base.py:88` `recover_locator(...)`
- `xpath_healer/api/base.py:209` `_build_rag_assist_from_env(...)`
- `xpath_healer/api/base.py:246` `_build_repository_from_env(...)`
- `adapters/playwright_python/facade.py:10` `PlaywrightHealerFacade`
- `adapters/selenium_python/facade.py:10` `SeleniumHealerFacade`

Capabilities:
- Resolves adapter and config.
- Builds validator/similarity/signature/snapshotter/page indexer/strategy registry.
- Creates `StrategyContext` and delegates healing to `HealingService`.
- Auto-wires RAG (OpenAI + Chroma retriever) only when key + DSN are valid.
- Auto-wires repository mode:
  - no DSN -> in-memory
  - DSN -> dual repository (Postgres primary + JSON fallback)

Adapter implementation management:
- Adapter selection is centralized in `create_healer_facade(...)`:
  - `xpath_healer/api/factory.py:24`
  - Resolved by `XH_ADAPTER` (`playwright_python` or `selenium_python`) via config/env.
- Playwright adapter implementation:
  - `adapters/playwright_python/adapter.py:48` `PlaywrightPythonAdapter`
  - `resolve_locator(...)` supports `css`, `xpath`, `pw`, `text`, `role`.
- Selenium adapter implementation:
  - `adapters/selenium_python/adapter.py:117` `SeleniumPythonAdapter`
  - `resolve_locator(...)` supports same locator kinds.
  - Runtime locator has stale-element retry in `_elements()`:
    - `adapters/selenium_python/adapter.py:36`
- Browser-variable mapping for integration execution is done in:
  - `tests/integration/settings.py:60` `XH_PLAYWRIGHT_BROWSER`
  - `tests/integration/settings.py:62` `XH_PLAYWRIGHT_CHANNEL`
  - `tests/integration/settings.py:64` `XH_SELENIUM_BROWSER`
  - `tests/integration/settings.py:65` `XH_SELENIUM_BINARY`
  - `tests/integration/settings.py:66` `XH_HEADLESS`

### 4.3 Core Healing Layer

Main file:
- `xpath_healer/core/healing_service.py`

Entry and stage orchestrator:
- `recover_locator(...)` at `:32`

Stage sequence inside `recover_locator(...)`:
1. fallback
2. metadata
3. rules
4. fingerprint
5. page_index
6. signature
7. dom_mining
8. defaults
9. position
10. rag (optional final stage)

Key methods:
- candidate evaluation (serial): `:209`
- candidate evaluation (parallel): `:267`
- validation retry loop: `:340`
- rag candidate build: `:817`
- rag retry reason policy: `:906`
- persist success: `:997`
- persist failure: `:1091`
- stage event logging: `:1099`

### 4.4 Storage Layer (DB + Fallback Stores)

Interface:
- `xpath_healer/store/repository.py:11` `MetadataRepository`

Implementations:
- In-memory: `xpath_healer/store/memory_repository.py`
- JSON: `xpath_healer/store/json_repository.py`
- Postgres: `xpath_healer/store/pg_repository.py:29`
- Dual primary/fallback: `xpath_healer/store/dual_repository.py`

Postgres methods:
- `find(...)` `pg_repository.py:88`
- `upsert(...)` `pg_repository.py:127`
- `find_candidates_by_page(...)` `pg_repository.py:208`
- `get_page_index(...)` `pg_repository.py:259`
- `upsert_page_index(...)` `pg_repository.py:348`
- `log_event(...)` `pg_repository.py:454`

Schema:
- `schema_sql()` at `pg_repository.py:1033`
- Includes `events`, `healing_events`, `rag_documents` tables at lines near `1121`, `1135`, `1150`.

### 4.5 Model/RAG Layer (Prompt + Context + LLM)

Main files:
- `xpath_healer/rag/rag_assist.py:16` `RagAssist`
- `xpath_healer/rag/rag_assist.py:34` `suggest(...)`
- `xpath_healer/rag/prompt_builder.py:14` `build_prompt_payload(...)`
- `xpath_healer/rag/prompt_dsl.py:11` `build_prompt_dsl(...)`
- `xpath_healer/rag/openai_llm.py:21` `OpenAILLM`
- `xpath_healer/rag/openai_llm.py:32` `suggest_locators(...)`

Capabilities:
- Builds query from current element intent + DOM signature.
- Embeds query, retrieves context, adds DOM-seeded context, reranks.
- Builds compact payload and DSL prompt.
- Calls OpenAI chat completion with strict JSON candidate contract.
- Normalizes and filters LLM candidates before returning to core validator.

### 4.6 Service Layer (HTTP API mode)

Main file:
- `service/main.py`

Endpoints:
- `POST /generate` at `service/main.py:75`
- `POST /heal` at `service/main.py:87`

Session resolution support:
- `service/session_registry.py:27` `resolve_session(...)`

## 5) End-to-End Call Flow (Integration)

Typical BDD step call chain:
1. BDD step calls `_heal(...)` in `tests/integration/test_demo_qa_healing_bdd.py:116`.
2. `_heal(...)` calls `healer.recover_locator(...)` at line `130`.
3. Facade receives call at `xpath_healer/api/base.py:88`.
4. Facade delegates to `HealingService.recover_locator(...)` at `xpath_healer/core/healing_service.py:32`.
5. Healing service runs stages, validates candidates, retries where allowed.
6. On success/failure, metadata/events are persisted via repository methods.
7. Integration hooks capture screenshots/videos/logs and produce HTML/JSON reports.

## 6) Database Methods in E2E Flow

Where DB backend is selected:
- `tests/integration/conftest.py:402` `metadata_repository(...)`
- If `XH_PG_DSN` set, backend is `DualMetadataRepository(Postgres + Json)` at line `415`.

Where DB operations are wrapped/logged:
- `LoggedMetadataRepository` methods in `tests/integration/conftest.py`:
  - `find(...)` `:144`
  - `upsert(...)` `:171`
  - `find_candidates_by_page(...)` `:200`
  - `get_page_index(...)` `:235`
  - `upsert_page_index(...)` `:260`
  - `log_event(...)` `:285`

Where core healing calls repository APIs:
- `find(...)` `healing_service.py:42`
- `find_candidates_by_page(...)` `healing_service.py:476`, `:483`, `:680`
- `get_page_index(...)` `healing_service.py:558`
- `upsert_page_index(...)` `healing_service.py:572`
- `upsert(...)` `healing_service.py:1088`, `:1097`
- `log_event(...)` `healing_service.py:1123`

Dual repository behavior:
- Read primary first, fallback on miss/error, warm primary from fallback.
- Dual-write where possible to both primary and fallback.
- Implemented in `xpath_healer/store/dual_repository.py`.

## 7) Prompt Creation, Context Ingestion, LLM Call, and Retry

### 7.1 Prompt creation + context ingestion

Prompt creation path:
1. `RagAssist.suggest(...)` at `rag_assist.py:34`
2. Build DOM signature + extract DOM context:
   - `build_dom_signature(...)` at `prompt_builder.py:71`
   - `extract_dom_context(...)` at `prompt_builder.py:111`
3. Retrieve context:
   - `retriever.retrieve(...)` call at `rag_assist.py:62`
4. Build payload:
   - `build_prompt_payload(...)` at `prompt_builder.py:14`
5. Build compact DSL prompt:
   - `build_prompt_dsl(...)` at `prompt_dsl.py:11`

### 7.2 LLM call location

- LLM adapter call is in `OpenAILLM.suggest_locators(...)`:
  - method at `openai_llm.py:32`
  - OpenAI request at `openai_llm.py:54` (`chat.completions.create(...)`)

### 7.3 Retry locations

Candidate validation retry:
- `HealingService._validate_candidate_with_retry(...)` at `healing_service.py:340`
- Uses `retry.max_attempts`, `retry.delay_ms`, `retry.retry_reason_codes`.

RAG deep retry:
- In `HealingService.recover_locator(...)`:
  - deep retry loop at `healing_service.py:149`
  - retry reason policy in `_rag_retry_reason(...)` at `:906`

Embedder fallback retry:
- `OpenAIEmbedder.embed_text(...)` retries without `dimensions` if first embedding request fails:
  - `xpath_healer/rag/openai_embedder.py:31`, `:39`

### 7.4 Where max retry config is updated

Environment-driven update points in `HealerConfig.from_env(...)`:
- `XH_PROMPT_GRAPH_DEEP_RETRY_MAX` -> `cfg.prompt.graph_deep_retry_max`
  - `xpath_healer/core/config.py:200-202`
- `XH_RETRY_MAX_ATTEMPTS` -> `cfg.retry.max_attempts`
  - `xpath_healer/core/config.py:246-248`

Code-level override examples in tests:
- `tests/unit/test_rag_deep_retry.py` sets `cfg.prompt.graph_deep_retry_max`.
- `tests/unit/test_healing_retry.py` sets `cfg.retry.max_attempts`.

## 8) Unit Test Coverage by Layer

### 8.1 Core healing + strategy/validation layer

- `tests/unit/test_healing_service.py`
- `tests/unit/test_healing_service_fingerprint.py`
- `tests/unit/test_healing_service_graph_context.py`
- `tests/unit/test_healing_retry.py`
- `tests/unit/test_page_indexing.py`
- `tests/unit/test_fingerprint.py`
- `tests/unit/test_similarity.py`
- `tests/unit/test_validator.py`
- `tests/unit/test_checkbox_proxy_validation.py`
- `tests/unit/test_strategy_registry.py`
- `tests/unit/test_stage_switches.py`
- `tests/unit/test_snapshotter.py`

### 8.2 Model/RAG layer

- `tests/unit/test_prompt_dsl.py`
- `tests/unit/test_rag_assist.py`
- `tests/unit/test_rag_deep_retry.py`

### 8.3 Store/DB layer

- `tests/unit/test_dual_repository.py`
- `tests/unit/test_pg_repository_schema.py`
- `tests/unit/test_models_serialization.py`

### 8.4 Facade/service/integration-settings layer

- `tests/unit/test_facade_repository_init.py`
- `tests/unit/test_facade_rag_init.py`
- `tests/unit/test_service_sessions.py`
- `tests/unit/test_integration_settings.py`

### 8.5 Adapter + utility layer

- `tests/unit/test_selenium_adapter.py`
- `tests/unit/test_text_utils.py`

## 9) How Tests Are Called

All unit tests:
```powershell
python -m pytest -q tests\unit
```

Single test module examples:
```powershell
python -m pytest -q tests\unit\test_healing_retry.py
python -m pytest -q tests\unit\test_rag_deep_retry.py
python -m pytest -q tests\unit\test_dual_repository.py
```

Playwright BDD integration:
```powershell
python -m pytest -q -rs -m "integration and not negative" tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json
```

Selenium integration:
```powershell
python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_selenium.py --junitxml=artifacts/reports/integration-junit.xml
```

## 10) NoSuchElement / Invalid XPath Exception Handling (Java catch/finally equivalent)

### 10.1 How this project avoids immediate test failure

The integration tests use a `heal-first` pattern, not `action-first`:
- Step helper creates intentionally broken fallback XPath:
  - `tests/integration/test_demo_qa_healing_bdd.py:112`
  - `tests/integration/test_demo_qa_healing_selenium.py:37`
- Then it directly calls `healer.recover_locator(...)`:
  - `tests/integration/test_demo_qa_healing_bdd.py:130`
  - `tests/integration/test_demo_qa_healing_selenium.py:150`
- So the raw invalid XPath is not executed as final action; it is only the first candidate in healing pipeline.

Inside healing core:
- Fallback stage runs first:
  - `xpath_healer/core/healing_service.py:55-57`
- If fallback candidate is invalid/no-match, it records fail and continues to next stages (metadata/rules/fingerprint/.../rag), instead of throwing.

### 10.2 Where exceptions are converted to reason codes (not hard failures)

Validator catches locator resolution/count exceptions:
- `xpath_healer/core/validator.py:18` `validate_candidate(...)`
- Catch block at `xpath_healer/core/validator.py:29`
- Exception -> reason code mapping in `_locator_error_reason(...)`:
  - `xpath_healer/core/validator.py:328`
  - Maps to `stale_element`, `locator_timeout`, or `locator_error`.

If locator resolves but finds nothing:
- Returns `ValidationResult.fail(["no_match"])` at `xpath_healer/core/validator.py:36`.

### 10.3 Retry behavior for transient locator exceptions

Healing retry loop:
- `xpath_healer/core/healing_service.py:340` `_validate_candidate_with_retry(...)`
- Retries only when reason code intersects configured retry codes:
  - `xpath_healer/core/healing_service.py:389`
- Defaults include:
  - `locator_error`, `locator_timeout`, `stale_element`, `not_visible`
  - `xpath_healer/core/config.py:102`

### 10.4 Why this is equivalent to Java catch/finally behavior

Equivalent behavior is split into framework + core:
- Java-style `catch`: handled inside validator/healing service as reason-code failures + retry, not uncaught exceptions.
- Java-style `finally`: handled in pytest fixtures/hooks for artifact/log capture and cleanup:
  - Playwright fixture cleanup `finally`: `tests/integration/conftest.py:485`
  - Selenium fixture cleanup `finally`: `tests/integration/test_demo_qa_healing_selenium.py:119`

### 10.5 Important distinction

- If you bypass healer and directly query invalid raw XPath, test fails by design in negative scenario:
  - `tests/integration/test_demo_qa_healing_bdd.py:502`
  - `tests/integration/test_demo_qa_healing_bdd.py:538`
- Normal positive flow should always call healer before action.
