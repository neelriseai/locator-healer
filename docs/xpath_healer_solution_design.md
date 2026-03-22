# XPath Healer Solution Design (Layered, Contract-First)

Version: 1.0
Date: 2026-03-02
Owner: XPath Healer Team
Status: Design baseline for Layer-2/3/4 implementation (DB, Service, Model/LLM)

## 1) Objective
Build the remaining layers around the existing deterministic core (`xpath_healer`) so teams can implement independently and still integrate without sharing internal core implementation details.

This design defines:
- architecture and layer boundaries
- strict input/output contracts
- project structure
- method names + definitions
- PostgreSQL/pgvector schema + CRUD behavior
- FastAPI service contract
- LLM/model call flow with prompt templates
- implementation prompts for AI assistants

## 2) Current Baseline (Already in Code)
Core healing engine already exists and is working in standalone mode:
- `XPathHealerFacade.recover_locator(...)`
- `HealingService` with deterministic cascade
- strategy registry + validators + signature extraction
- metadata repositories: in-memory + JSON
- FastAPI thin wrapper exists (`service/main.py`)
- BDD integration tests (Playwright + pytest-bdd)

So remaining work is production-grade DB layer, service hardening, and model/RAG layer implementation.

## 3) Non-Negotiable Integration Contract
All teams must align on these core domain objects (JSON-serializable):
- `LocatorSpec`:
  - `kind: css|xpath|role|text|pw`
  - `value: str`
  - `options: dict`
  - `scope: LocatorSpec | None`
- `Intent`:
  - parsed from `vars` (label, text, axis_hint, occurrence, match_mode, strict flags)
- `HealingHints`:
  - attr priority, threshold, visibility/strict settings
- `ElementMeta`:
  - persisted metadata (last good locator, variants, signature, quality metrics, counters)
- `Recovered`:
  - runtime result (`status`, `locator_spec`, `strategy_id`, `trace`, `correlation_id`)
- `StrategyTrace`:
  - stage-wise observability payload

Compatibility rule:
- Service and DB layers must not mutate the semantic meaning of these fields.
- Additive fields are allowed; breaking renames are not.

## 4) Target Architecture

```text
Playwright Test/Client
        |
        v
FastAPI Service Layer (transport + auth + session mgmt + DTO mapping)
        |
        v
Application Orchestration Layer (Facade + HealingService)
        |
        +--> Deterministic Core (strategies, validator, signature, similarity)
        |
        +--> Repository Interface (MetadataRepository)
        |        |
        |        +--> PostgresMetadataRepository (asyncpg + pgvector)
        |
        +--> Optional RAG Assist
                 |
                 +--> Embedder (OpenAI embeddings)
                 +--> Retriever (pgvector semantic search)
                 +--> LLM (GPT-4.1 suggestion only)
```

Design principles:
- deterministic-first
- LLM is assistive, never authoritative
- every candidate is validated by `XPathValidator`
- every stage emits trace events

## 5) Layer Responsibilities and I/O Expectations

### 5.1 Core Layer (existing)
Primary method:
- `XPathHealerFacade.recover_locator(page, app_id, page_name, element_name, field_type, fallback, vars, hints=None) -> Recovered`

Input expectations:
- `fallback` can be invalid intentionally
- `vars` provides contextual hints (label/text/axis/position)
- `page` is an active Playwright `Page`

Output expectations:
- `status` is `success` or `failed`
- on success, `locator_spec` is usable immediately
- `trace` always contains stage attempt details
- `metadata` contains updated signatures/variants/quality metrics

### 5.2 DB Layer (to implement)
Implements `MetadataRepository` contract:
- `find(app_id, page_name, element_name) -> ElementMeta | None`
- `upsert(meta) -> None`
- `find_candidates_by_page(app_id, page_name, field_type, limit=25) -> list[ElementMeta]`
- `log_event(event: dict) -> None`

Input expectations:
- domain objects from core, already validated structurally
- no business logic mutation in repository

Output expectations:
- full fidelity serialization/deserialization of domain models
- stable ordering from `find_candidates_by_page` (latest/high-signal first)

### 5.3 Service Layer (to implement/harden)
FastAPI provides transport and operational controls.

Input expectations:
- JSON DTOs mapped to domain models
- session-bound browser page for `/heal`

Output expectations:
- deterministic response envelope
- trace and correlation id always returned
- non-2xx errors include actionable details

### 5.4 Model/LLM Layer (to implement)
Implements adapters:
- `Embedder.embed_text(text) -> list[float]`
- `Retriever.retrieve(query_embedding, top_k) -> list[dict]`
- `LLM.suggest_locators(prompt_payload) -> list[dict]`

Input expectations:
- bounded DOM/context payloads
- strict prompt schema

Output expectations:
- only structured locator suggestions
- invalid/unsafe output discarded before core validation

## 6) Recommended Final Project Structure

```text
xpath_healer/
  api/
    facade.py
  core/
    models.py
    config.py
    context.py
    strategy_registry.py
    builder.py
    validator.py
    signature.py
    similarity.py
    healing_service.py
    strategies/
  store/
    repository.py
    memory_repository.py
    json_repository.py
    pg_repository.py              # implement fully
    pg_sql.py                     # NEW: SQL constants + migrations helper
  rag/
    embedder.py
    retriever.py
    llm.py
    rag_assist.py
    openai_embedder.py            # NEW
    pgvector_retriever.py         # NEW
    openai_llm.py                 # NEW
    prompt_builder.py             # NEW
service/
  main.py
  deps.py                         # NEW: DI wiring
  schemas.py                      # NEW: request/response DTOs
  sessions.py                     # NEW: Playwright session registry
  settings.py                     # NEW: env config
  middleware.py                   # NEW: correlation-id, logging, timing
docs/
  xpath_healer_solution_design.md
  xpath_healer_solution_design.rtf
tests/
  unit/
  integration/
  contract/                       # NEW: API + repository contract tests
```

## 7) Database Design (PostgreSQL + pgvector)

### 7.1 Extensions
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

### 7.2 Tables

#### Table: `elements`
Purpose: source of truth per logical element.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | no | default `gen_random_uuid()` |
| app_id | text | no | tenant/app key |
| page_name | text | no | logical page |
| element_name | text | no | logical element key |
| field_type | text | no | textbox/button/checkbox/... |
| last_good_locator | jsonb | yes | `LocatorSpec` |
| robust_locator | jsonb | yes | robust fallback locator |
| strategy_id | text | yes | latest successful strategy |
| signature | jsonb | yes | `ElementSignature` |
| signature_embedding | vector(1536) | yes | embedding of serialized signature |
| hints | jsonb | yes | `HealingHints` |
| locator_variants | jsonb | yes | `last_good`, `robust_xpath`, `live_xpath`, etc |
| quality_metrics | jsonb | yes | uniqueness/stability/similarity/history |
| last_seen | timestamptz | no | default now() |
| success_count | int4 | no | default 0 |
| fail_count | int4 | no | default 0 |

Constraints:
- `PRIMARY KEY(id)`
- `UNIQUE(app_id, page_name, element_name)`

Indexes:
```sql
CREATE INDEX IF NOT EXISTS idx_elements_app_page_field
  ON elements(app_id, page_name, field_type);

CREATE INDEX IF NOT EXISTS idx_elements_last_seen
  ON elements(last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_elements_strategy
  ON elements(strategy_id);

CREATE INDEX IF NOT EXISTS idx_elements_signature_embedding
  ON elements USING ivfflat (signature_embedding vector_cosine_ops)
  WITH (lists = 100);
```

#### Table: `events`
Purpose: stage-level observability/audit.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigserial | no | PK |
| correlation_id | text | no | request/run trace |
| timestamp | timestamptz | no | default now() |
| app_id | text | yes | |
| page_name | text | yes | |
| element_name | text | yes | |
| field_type | text | yes | |
| stage | text | yes | fallback/metadata/rules/... |
| status | text | yes | ok/fail |
| score | double precision | yes | strategy score |
| details | jsonb | yes | locator + validation payload |

Indexes:
```sql
CREATE INDEX IF NOT EXISTS idx_events_corr ON events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_lookup ON events(app_id, page_name, element_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_stage_status ON events(stage, status);
```

#### Optional table: `rag_documents`
Purpose: store chunked metadata and embeddings for retrieval.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | bigserial | no | PK |
| app_id | text | no | |
| page_name | text | no | |
| element_name | text | yes | nullable for page-level docs |
| source | text | no | `metadata|event|manual` |
| chunk_text | text | no | chunked context |
| embedding | vector(1536) | yes | semantic search |
| metadata | jsonb | yes | arbitrary tags |
| created_at | timestamptz | no | default now() |

## 8) CRUD Contract (DB Layer)

### 8.1 Create/Update Element (Upsert)
```sql
INSERT INTO elements (
  app_id, page_name, element_name, field_type,
  last_good_locator, robust_locator, strategy_id,
  signature, signature_embedding, hints,
  locator_variants, quality_metrics,
  last_seen, success_count, fail_count
)
VALUES (
  $1,$2,$3,$4,
  $5::jsonb,$6::jsonb,$7,
  $8::jsonb,$9,$10::jsonb,
  $11::jsonb,$12::jsonb,
  now(),$13,$14
)
ON CONFLICT (app_id, page_name, element_name)
DO UPDATE SET
  field_type = EXCLUDED.field_type,
  last_good_locator = EXCLUDED.last_good_locator,
  robust_locator = EXCLUDED.robust_locator,
  strategy_id = EXCLUDED.strategy_id,
  signature = EXCLUDED.signature,
  signature_embedding = COALESCE(EXCLUDED.signature_embedding, elements.signature_embedding),
  hints = EXCLUDED.hints,
  locator_variants = EXCLUDED.locator_variants,
  quality_metrics = EXCLUDED.quality_metrics,
  last_seen = now(),
  success_count = EXCLUDED.success_count,
  fail_count = EXCLUDED.fail_count;
```

### 8.2 Read Element by Logical Key
```sql
SELECT *
FROM elements
WHERE app_id=$1 AND page_name=$2 AND element_name=$3
LIMIT 1;
```

### 8.3 Read Candidate Elements by Page
```sql
SELECT *
FROM elements
WHERE app_id=$1
  AND page_name=$2
  AND ($3 = '' OR field_type=$3)
ORDER BY success_count DESC, last_seen DESC
LIMIT $4;
```

### 8.4 Log Event
```sql
INSERT INTO events (
  correlation_id, app_id, page_name, element_name, field_type,
  stage, status, score, details
)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb);
```

### 8.5 Vector Similarity Retrieval (optional)
```sql
SELECT id, app_id, page_name, element_name, source, chunk_text, metadata,
       1 - (embedding <=> $1::vector) AS similarity
FROM rag_documents
WHERE app_id=$2
ORDER BY embedding <=> $1::vector
LIMIT $3;
```

## 9) DB Layer: Required Classes/Methods

### `xpath_healer.store.pg_repository.PostgresMetadataRepository`
Constructor:
- `__init__(dsn: str, pool_min_size: int = 1, pool_max_size: int = 10)`

Methods:
1. `async connect() -> None`
   - open asyncpg pool
2. `async close() -> None`
   - close pool cleanly
3. `async init_schema() -> None`
   - execute extension/table/index DDL
4. `async find(app_id, page_name, element_name) -> ElementMeta | None`
   - map row -> `ElementMeta.from_dict(...)`
5. `async upsert(meta: ElementMeta) -> None`
   - atomic upsert + metrics preservation
6. `async find_candidates_by_page(app_id, page_name, field_type, limit=25) -> list[ElementMeta]`
   - deterministic ordering
7. `async log_event(event: dict[str, Any]) -> None`
   - insert event row
8. `async find_similar_signatures(app_id: str, embedding: list[float], top_k: int) -> list[dict]` (optional helper)
   - used by retriever/RAG

Definition of done:
- contract tests pass against same test matrix as `JsonMetadataRepository`
- serialization fidelity proven via round-trip tests

## 10) Service Layer Design (FastAPI)

### 10.1 Service Endpoints

1. `GET /health`
   - output: `{ "status": "ok" }`

2. `POST /sessions/open`
   - input: `{ "browser": "chromium|chrome|firefox", "headless": true, "base_url": "..." }`
   - output: `{ "session_id": "...", "created_at": "..." }`

3. `POST /sessions/{session_id}/close`
   - closes Playwright context/page

4. `POST /heal`
   - input mirrors `HealRequest`
   - output mirrors `Recovered` envelope

5. `POST /generate`
   - input mirrors `GenerateRequest`
   - output: `{ "locator_spec": {...} }`

6. `GET /metadata/{app_id}/{page_name}/{element_name}`
   - output: persisted `ElementMeta`

7. `POST /metadata/search`
   - input: `{ "app_id": "...", "page_name": "...", "field_type": "...", "limit": 25 }`
   - output: `elements: [...]`

### 10.2 Service Methods (Application Layer)
Create `service/deps.py` with:
- `get_settings() -> ServiceSettings`
- `get_repository() -> MetadataRepository`
- `get_healer() -> XPathHealerFacade`
- `get_page_resolver() -> PageResolver`

Create `service/sessions.py` with:
- `open_session(...) -> str`
- `resolve_page(session_id: str) -> Page | None`
- `close_session(session_id: str) -> bool`
- `shutdown_all() -> None`

### 10.3 Error/Status Policy
- 400: invalid request payload
- 404: unknown session/metadata key
- 422: schema validation
- 503: page resolver unavailable
- 500: unexpected server error

Every non-2xx response includes:
- `correlation_id`
- `error_code`
- `message`
- `details` (optional)

## 11) Model Layer (OpenAI + pgvector)

### 11.1 Adapter Implementations

#### `xpath_healer.rag.openai_embedder.OpenAIEmbedder(Embedder)`
- `__init__(api_key: str | None = None, model: str = "text-embedding-3-large", dimensions: int | None = None)`
- `async embed_text(text: str) -> list[float]`

Behavior:
- call embeddings API
- normalize empty input rejection
- retry/backoff on 429/5xx

#### `xpath_healer.rag.pgvector_retriever.PgVectorRetriever(Retriever)`
- `__init__(pool, app_id: str | None = None)`
- `async retrieve(query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]`

Behavior:
- execute similarity query on `rag_documents` or `elements.signature_embedding`
- return compact context objects only

#### `xpath_healer.rag.openai_llm.OpenAILLM(LLM)`
- `__init__(api_key: str | None = None, model: str = "gpt-4.1")`
- `async suggest_locators(prompt_payload: dict[str, Any]) -> list[dict[str, Any]]`

Behavior:
- send strict prompt + JSON schema requirement
- parse JSON safely
- drop invalid suggestions

### 11.2 Exact LLM Call Pattern (Python)
Use official OpenAI Python SDK pattern (`responses.create`) and embeddings endpoint (`embeddings.create`).

Pseudo-code:
```python
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

resp = client.responses.create(
    model="gpt-4.1",
    input=prompt_text,
    temperature=0,
)
text = resp.output_text

emb = client.embeddings.create(
    model="text-embedding-3-large",
    input=query_text,
)
vector = emb.data[0].embedding
```

Integration rule:
- LLM output is never used directly; convert to `LocatorSpec` and validate via `XPathValidator`.

## 12) Prompt Design for RAG/LLM Stage

### 12.1 System Prompt (strict)
```
You are a locator suggestion engine for Playwright.
Return ONLY valid JSON array.
Each item must contain: {"kind": "css|xpath|role|text|pw", "value": "...", "options": {...}}.
Rules:
1) Prefer robust selectors using stable attrs: data-testid, aria-label, name, formcontrolname, role, col-id.
2) Avoid deep absolute XPath and volatile class chains.
3) Use text/role only when unambiguous.
4) Maximum 5 candidates, best first.
5) Do not explain, do not include markdown.
```

### 12.2 User Prompt Template
```
Task: Suggest locator candidates for a broken element.
Field type: {field_type}
Intent: {intent_json}
Vars: {vars_json}
DOM snippet: {dom_snippet}
Retrieved context: {context_json}
Output: JSON array of LocatorSpec-compatible objects.
```

### 12.3 Candidate Post-Processing
For each LLM candidate:
1. parse json -> `LocatorSpec`
2. reject weak locators (`//*`, `/html[1]`, `*`, `html`)
3. run `validate_candidate(...)`
4. first validated candidate wins
5. append trace event (`stage=rag`, `status=ok|fail`)

## 13) End-to-End Sequence

1. Client sends `/heal` with broken fallback + vars.
2. Service resolves Playwright page by `session_id`.
3. `XPathHealerFacade.recover_locator(...)` executes cascade.
4. On each stage, validator gates candidate.
5. On success:
   - persist `ElementMeta` via repository
   - log events
   - return `Recovered` payload
6. On full failure:
   - return failed `Recovered` with full trace

## 14) Standard Method Definitions (Team Checklist)

### Core-facing methods (must match)
- `recover_locator(...) -> Recovered`
- `generate_locator_async(...) -> LocatorSpec`
- `validate_candidate(...) -> ValidationResult`

### Repository methods (must match)
- `find(...) -> ElementMeta | None`
- `upsert(...) -> None`
- `find_candidates_by_page(...) -> list[ElementMeta]`
- `log_event(...) -> None`

### Service methods (must provide)
- `create_app(...) -> FastAPI`
- `open_session(...)`, `close_session(...)`, `resolve_page(...)`

### Model/RAG methods (must provide)
- `Embedder.embed_text(...)`
- `Retriever.retrieve(...)`
- `LLM.suggest_locators(...)`
- `RagAssist.suggest(...) -> list[LocatorSpec]`

## 15) AI Assistant Implementation Prompts (Copy/Paste)

### Prompt A: DB Layer
```
Implement xpath_healer/store/pg_repository.py using asyncpg and pgvector.
Requirements:
- Fully implement MetadataRepository methods: find, upsert, find_candidates_by_page, log_event.
- Add connect/close/init_schema helpers.
- Store and load ElementMeta exactly using existing to_dict/from_dict structure.
- Persist locator_variants and quality_metrics jsonb columns.
- Ensure upsert on unique(app_id,page_name,element_name).
- Add deterministic ordering for candidates: success_count desc, last_seen desc.
- Add tests in tests/unit/test_pg_repository.py using temporary PostgreSQL.
Do not change public signatures in repository.py.
```

### Prompt B: Service Layer
```
Refactor service layer into modules: main.py, schemas.py, deps.py, sessions.py, settings.py.
Add endpoints:
- GET /health
- POST /sessions/open
- POST /sessions/{session_id}/close
- POST /generate
- POST /heal
- GET /metadata/{app_id}/{page_name}/{element_name}
Use existing XPathHealerFacade contracts.
Return correlation_id on all error responses.
Add integration tests for endpoint behavior with mocked page resolver.
```

### Prompt C: Model/LLM Layer
```
Implement adapters:
- xpath_healer/rag/openai_embedder.py (Embedder)
- xpath_healer/rag/openai_llm.py (LLM)
- xpath_healer/rag/pgvector_retriever.py (Retriever)
Use OpenAI Python SDK.
- embeddings.create for vectors
- responses.create for locator suggestion text
Prompt must force strict JSON array output.
Parse output defensively and drop invalid candidates.
Add retries (429/5xx) and timeout handling.
Add unit tests with mocked OpenAI client.
```

### Prompt D: Integration Wiring
```
Wire optional RAG into XPathHealerFacade construction:
- if XH_RAG_ENABLED=true and OPENAI_API_KEY present, instantiate OpenAIEmbedder + PgVectorRetriever + OpenAILLM + RagAssist
- pass rag_assist into StrategyContext
- keep deterministic behavior unchanged when RAG is disabled.
Add tests proving deterministic path still works without OpenAI key.
```

## 16) Configuration Matrix

Environment keys (minimum):
- `OPENAI_API_KEY`
- `XH_DB_DSN`
- `XH_RAG_ENABLED`
- `XH_RAG_TOP_K`
- `XH_OPENAI_MODEL` (default `gpt-4.1`)
- `XH_EMBED_MODEL` (default `text-embedding-3-large`)
- `XH_SERVICE_HOST`, `XH_SERVICE_PORT`

Behavior:
- Missing OpenAI key => run deterministic-only mode.
- Missing pgvector extension => disable embedding retrieval, keep metadata CRUD active.

## 17) Quality Gates

Mandatory tests:
1. Repository contract parity: JSON repo vs PG repo return equivalent `ElementMeta`.
2. Service contract tests: request/response schema and error mapping.
3. RAG safety tests: invalid JSON output from LLM is ignored safely.
4. Regression suite: existing integration BDD scenarios remain green (except intentional negative case).

Non-functional:
- p95 `/heal` latency target: < 300ms deterministic path (excluding browser action)
- no secrets logged
- correlation_id in every trace/event

## 18) Integration Readiness Checklist

- [ ] `PostgresMetadataRepository` implemented and contract-tested
- [ ] DB migrations/DDL applied in all environments
- [ ] Service session management implemented
- [ ] OpenAI adapters implemented behind feature flags
- [ ] RAG stage enabled only when configured
- [ ] Docs + sample curl requests published
- [ ] CI runs unit + integration + contract tests

## 19) OpenAI Reference Links (for implementation accuracy)
- Responses API reference: https://platform.openai.com/docs/api-reference/responses
- Embeddings API reference: https://platform.openai.com/docs/api-reference/embeddings
- GPT-4.1 model page: https://platform.openai.com/docs/models/gpt-4.1
- text-embedding-3-large model page: https://platform.openai.com/docs/models/text-embedding-3-large
- Python quickstart: https://platform.openai.com/docs/guides/code


## 20) Core Code + Prompt Pack (Parity Appendix)

This appendix is for generating the same project shape and behavior from prompts, including core healer and Playwright automation suite.

### 20.1 Scope of “same”
Target parity means:
- same package/file structure
- same public method names/signatures
- same healing cascade ordering and validation behavior
- same test scenarios and artifact behavior

For byte-for-byte parity, enforce with acceptance tests and checksum comparison (Section 20.8).

### 20.2 Exact Project Structure to Generate

```text
xpath_healer/
  __init__.py
  api/
    __init__.py
    facade.py
  core/
    __init__.py
    builder.py
    config.py
    context.py
    exceptions.py
    healing_service.py
    models.py
    signature.py
    similarity.py
    strategy_registry.py
    validator.py
    strategies/
      __init__.py
      base.py
      attribute_strategy.py
      axis_hint_field.py
      button_text_candidate.py
      checkbox_icon_by_label.py
      composite_label_control.py
      generic_template.py
      grid_cell_colid.py
      multi_field_text_resolver.py
      position_fallback.py
      text_occurrence.py
  dom/
    __init__.py
    mine.py
    snapshot.py
  rag/
    __init__.py
    embedder.py
    llm.py
    rag_assist.py
    retriever.py
  store/
    __init__.py
    repository.py
    memory_repository.py
    json_repository.py
    pg_repository.py
  utils/
    __init__.py
    ids.py
    logging.py
    text.py
    timing.py
service/
  __init__.py
  main.py
tests/
  __init__.py
  conftest.py
  unit/
    __init__.py
    fakes.py
    test_checkbox_proxy_validation.py
    test_healing_service.py
    test_models_serialization.py
    test_similarity.py
    test_strategy_registry.py
    test_text_utils.py
    test_validator.py
  integration/
    __init__.py
    config.json
    conftest.py
    settings.py
    test_demo_qa_healing_bdd.py
    features/
      demo_qa_healing.feature
README.md
pyproject.toml
```

### 20.3 Mandatory Public Contracts (must match exactly)

Core API:
- `XPathHealerFacade.recover_locator(page, app_id, page_name, element_name, field_type, fallback, vars, hints=None) -> Recovered`
- `XPathHealerFacade.generate_locator_async(page_name, element_name, field_type, vars, hints=None) -> LocatorSpec`
- `XPathHealerFacade.generate_locator(...) -> LocatorSpec`
- `XPathHealerFacade.validate_candidate(page, locator, field_type, intent) -> ValidationResult`

Service API:
- `create_app(facade=None, page_resolver=None) -> FastAPI`
- endpoints: `/health`, `/generate`, `/heal`

Repository interface:
- `find(...)`
- `upsert(...)`
- `find_candidates_by_page(...)`
- `log_event(...)`

### 20.4 Healing Cascade Contract (must match)
`HealingService.recover_locator` must execute in this order:
1. fallback
2. metadata reuse
3. rules/templates
4. signature similarity
5. dom mining
6. rag (optional)
7. defaults
8. position fallback

And must:
- validate every candidate through `XPathValidator`
- append `StrategyTrace` entries per attempt
- persist success/failure stats
- return `Recovered(status, locator_spec, strategy_id, trace, correlation_id)`

### 20.5 Master Prompt (Generate Same Core)
Use this as a single-shot prompt for any AI coding assistant.

```text
You are generating a Python 3.11+ project named xpath-healer.
Goal: create deterministic-first locator healing engine with the exact file structure and contracts listed below.

Hard constraints:
1) Use async Playwright integration points.
2) Implement dataclass domain models: LocatorSpec, HealingHints, Intent, ValidationResult, ElementSignature, ElementMeta, StrategyTrace, Recovered, BuildInput, CandidateSpec.
3) Implement HealingService cascade in exact order: fallback -> metadata -> rules -> signature -> dom mining -> rag(optional) -> defaults -> position.
4) Every candidate must be validated by XPathValidator.validate_candidate.
5) Metadata persistence contract must match MetadataRepository interface.
6) Include in-memory and JSON repositories; pg repository stub with schema_sql.
7) Include FastAPI wrapper service/main.py with /health, /generate, /heal.
8) Include pytest unit tests + pytest-bdd integration suite.
9) Keep outputs JSON-serializable.
10) Preserve deterministic behavior when rag is disabled.

Generate these files exactly:
[paste Section 20.2 tree]

Implement these public methods exactly:
[paste Section 20.3 list]

Implement these behaviors exactly:
- type-aware validation gates for button/link/textbox/dropdown/checkbox/radio/grid/text
- signature capture + robust css/xpath variant generation
- quality_metrics with uniqueness, stability, similarity, overall
- trace logging and event logging
- metadata locator_variants: last_good, robust_css, robust_xpath, live_css, live_xpath

Automation suite requirements:
- pytest-bdd feature with 4 scenarios (TC1..TC4) as defined in Section 21.1
- screenshots per step + final + failure
- one video per test
- reports: cucumber json, junit xml, steps jsonl, healing-calls jsonl, html report

Output format:
- emit each file as:
  ### FILE: <relative/path>
  ```python|json|toml|md
  <content>
  ```
- no extra commentary.
```

### 20.6 Sequenced Prompts (Preferred for Accurate Reconstruction)

Prompt 1: bootstrap
```text
Create pyproject.toml and README.md for xpath-healer.
Dependencies:
- playwright, fastapi, uvicorn
Optional extras:
- similarity: rapidfuzz
- dom: beautifulsoup4, lxml
- db: asyncpg, pgvector
- llm: openai
- dev: pytest, pytest-asyncio, pytest-bdd
Add pytest markers: integration, negative.
```

Prompt 2: core models and config
```text
Implement xpath_healer/core/models.py and config.py with exact domain dataclasses and env-driven HealerConfig.
Include LocatorSpec.to_playwright_locator supporting kinds css|xpath|role|text|pw and options exact, has_text, nth, first, last.
```

Prompt 3: strategy framework
```text
Implement Strategy base class, StrategyRegistry, XPathBuilder, StrategyContext.
Ensure StrategyRegistry sorts by priority and deduplicates by locator stable hash.
```

Prompt 4: validator + signature + similarity
```text
Implement XPathValidator with type-aware gates and axis/geometry checks.
Implement SignatureExtractor.capture + build_robust_locator + build_robust_xpath.
Implement SimilarityService scoring with threshold.
```

Prompt 5: healing orchestrator
```text
Implement HealingService.recover_locator and all helper methods.
Ensure stage event logging, trace entries, metadata persistence, locator_variants updates, and quality_metrics history.
```

Prompt 6: strategies
```text
Implement these strategy modules under xpath_healer/core/strategies:
- generic_template
- axis_hint_field
- composite_label_control
- checkbox_icon_by_label
- button_text_candidate
- multi_field_text_resolver
- attribute_strategy
- grid_cell_colid
- text_occurrence
- position_fallback
```

Prompt 7: repositories
```text
Implement repository interface + InMemoryMetadataRepository + JsonMetadataRepository and PostgresMetadataRepository skeleton with schema_sql.
```

Prompt 8: API facade + service
```text
Implement XPathHealerFacade and service/main.py with FastAPI endpoints /health /generate /heal and pydantic models.
```

Prompt 9: unit tests
```text
Add tests for validator, healing_service, similarity, models serialization, strategy registry, checkbox proxy behavior, text utils.
```

Prompt 10: playwright bdd automation
```text
Add tests/integration suite exactly as in Section 21:
- config-driven browser/artifacts setup
- feature file with TC1-TC4
- step definitions using intentionally broken fallback xpath and healer recovery
- html report generation with step and healing details
- screenshot/video capture behavior
```

### 20.7 File-Level Method Inventory (Quick Lock)

Core classes/method families expected:
- `xpath_healer/core/models.py`: all domain dataclasses listed in 20.3
- `xpath_healer/core/healing_service.py`: `recover_locator`, `_evaluate_candidates`, `_metadata_candidates`, `_signature_candidates`, `_dom_mining_candidates`, `_rag_candidates`, `_on_success`, `_persist_success`, `_persist_failure`, `_log_stage_event`, `_capture_live_locator_variants`, quality scoring helpers
- `xpath_healer/core/validator.py`: `validate_candidate`, type gates, axis/geometry checks
- `xpath_healer/api/facade.py`: constructor wiring + `recover_locator`, `generate_locator_async`, `generate_locator`, `validate_candidate`, `persist_success`, `register_strategy`
- `xpath_healer/store/repository.py`: abstract contract methods
- `service/main.py`: DTO models + `create_app`

### 20.8 Checksum/Parity Verification
After generation, run:

```powershell
python -m compileall -q .
python -m pytest -q tests\unit
python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json
```

Expected integration outcome:
- 3 passed
- 1 failed (intentional negative TC4)

Optional parity lock:
- generate `sha256` checksums for all `.py/.json/.toml/.feature` files
- compare against reference manifest before merge

## 21) Playwright Automation Suite (Detailed, Prompt-Ready)

### 21.1 Feature Scenarios (must match)
File: `tests/integration/features/demo_qa_healing.feature`

```gherkin
Feature: Demo QA App healing with broken fallback xpaths
  As a test automation engineer
  I want locator healing to recover target web elements from context anchors
  So that broken xpaths do not fail end-to-end tests

  Scenario: TC1 text-box form fill and submit
    Given I open the "text-box" demo page
    When I heal and fill all text-box form fields
    And I heal and click the text-box submit button
    Then I should see submitted text-box output values
    And trace logs should contain expected healing stages

  Scenario: TC2 checkbox Home icon select and message verify
    Given I open the "checkbox" demo page
    When I heal and click the Home checkbox icon
    Then I should see checkbox selection message for Home
    And trace logs should contain expected healing stages

  Scenario: TC3 webtables first row verification
    Given I open the "webtables" demo page
    When I heal and verify the first row first name is "Cierra"
    Then I heal and verify the first row last name is one of:
      | last_name |
      | Veha      |
      | Vega      |
    And trace logs should contain expected healing stages

  @negative
  Scenario: TC4 raw fallback xpath fails without healer
    Given I open the "text-box" demo page
    When I query raw invalid fallback xpath without healer
    Then report and logs should show xpath failure reason
```

### 21.2 Integration Config Contract
File: `tests/integration/config.json`

- base URL: `https://demo-qa-app.azurewebsites.net`
- browser engine/channel/headless configurable
- artifact paths:
  - reports: `artifacts/reports`
  - logs: `artifacts/logs`
  - screenshots: `artifacts/screenshots`
  - videos: `artifacts/videos`
  - metadata: `artifacts/metadata`
- capture flags:
  - `screenshot_each_test=true`
  - `screenshot_on_failure=true`
  - `screenshot_each_step=true`
  - `video_each_test=true`

### 21.3 Step Definition Behavior Contract
File: `tests/integration/test_demo_qa_healing_bdd.py`

Mandatory behavior:
- use intentionally invalid fallback xpath `//xh-never-match[...]`
- call healer with contextual vars (`label`, `text`, `axisHint`, `occurrence`, etc.)
- assert `Recovered.status == success` for positive steps
- append per-call records to `healing-calls.jsonl`
- include `selected_locator_kind/value`, `healed_xpath`, `healed_css`, and source fields
- TC4 explicitly fails using `pytest.fail(...)` after logging failure reason

### 21.4 Hooks/Reporting Contract
File: `tests/integration/conftest.py`

Mandatory behavior:
- cleanup old artifacts before session
- capture step-level screenshots and error screenshots
- capture final screenshot for every test
- capture one `.webm` per test and rename with test name
- write step events to `steps.jsonl`
- generate HTML report `integration-report.html` with:
  - step details table
  - healing-calls table
  - links to JSON/JUnit/video/metadata artifacts

### 21.5 Automation Generation Prompt (Copy/Paste)

```text
Generate pytest-bdd + Playwright integration suite for xpath-healer.
Requirements:
1) Create tests/integration/config.json with browser/artifact/capture settings.
2) Create settings loader (env override support).
3) Create conftest hooks for:
   - browser/page lifecycle
   - per-step and per-test screenshots
   - per-test videos
   - JSONL step report
   - custom HTML integration report
4) Create feature file with exact TC1-TC4 scenarios.
5) Create step definitions that:
   - use intentionally broken fallback xpath
   - call XPathHealerFacade.recover_locator
   - verify text-box, checkbox, webtables flows
   - include negative TC4 failure without healer
6) Ensure artifacts are written to artifacts/reports, artifacts/logs, artifacts/screenshots, artifacts/videos.
7) Ensure run command:
   python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json
Expected result: 3 passed, 1 failed (intentional negative case).
```

## 22) “Ditto Code” Delivery Protocol for Teams

To keep independently developed layers in sync:
1. Freeze this document as versioned contract (`docs/xpath_healer_solution_design.*`).
2. Implement layer branches separately (DB/service/model).
3. Run contract test pack + integration suite after each merge.
4. Reject merge if any public method signature or response schema drifts.
5. Track schema/prompt changes with semantic versioning:
   - patch: non-breaking internals
   - minor: additive fields/endpoints
   - major: any breaking contract change
