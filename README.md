# XPath Healer

Deterministic-first locator healing engine with configurable automation adapters, with:
- strategy-based candidate generation
- type-aware validation gates
- signature/similarity scoring
- first-run DOM mining fallback
- in-memory metadata store for standalone operation
- thin FastAPI wrapper

Current adapters:
- `adapters/playwright_python`
- `adapters/selenium_python`

## Quick Start

```bash
python -m pip install -e .[dev,similarity,dom]
python -m pytest -q
```

## Library Usage

```python
from adapters.playwright_python.facade import PlaywrightHealerFacade
from adapters.selenium_python.facade import SeleniumHealerFacade
from xpath_healer.core.models import LocatorSpec

playwright_facade = PlaywrightHealerFacade()
selenium_facade = SeleniumHealerFacade()

# inside async Playwright flow
recovered = await playwright_facade.recover_locator(
    page=page,
    app_id="demo-app",
    page_name="login",
    element_name="username",
    field_type="textbox",
    fallback=LocatorSpec(kind="xpath", value="//input[@id='dynamic-id']"),
    vars={"label": "Username", "data-testid": "username-input"},
)
```

You can also select the adapter through config/env with `XH_ADAPTER=playwright_python` or `XH_ADAPTER=selenium_python` and create the facade via `xpath_healer.create_healer_facade()`.

Integration browser selection is explicit per framework:
- Playwright: `XH_PLAYWRIGHT_BROWSER=chromium|chrome|edge|firefox|webkit`
- Playwright channel override: `XH_PLAYWRIGHT_CHANNEL=chrome|msedge|...`
- Selenium: `XH_SELENIUM_BROWSER=chrome|chromium|edge|firefox`
- Selenium Chromium binary override: `XH_SELENIUM_BINARY=/path/to/chromium`

## API

Run FastAPI wrapper:

```bash
uvicorn service.main:app --reload
```

## Optional DB + RAG Config

Create an `.env` (or set shell env vars) with placeholders:

```bash
OPENAI_API_KEY=<your-openai-key-placeholder>
XH_OPENAI_LLM_API_KEY=
XH_OPENAI_EMBED_API_KEY=
XH_OPENAI_PROVIDER=openai
# Azure OpenAI optional:
XH_AZURE_OPENAI_ENDPOINT=
XH_AZURE_OPENAI_API_VERSION=
XH_AZURE_OPENAI_DEPLOYMENT=
XH_AZURE_OPENAI_CHAT_ENDPOINT=
XH_AZURE_OPENAI_CHAT_API_VERSION=
XH_AZURE_OPENAI_CHAT_DEPLOYMENT=
XH_AZURE_OPENAI_EMBED_ENDPOINT=
XH_AZURE_OPENAI_EMBED_API_VERSION=
XH_AZURE_OPENAI_EMBED_DEPLOYMENT=
XH_PG_DSN=postgresql://<user>:<password>@<host>:5432/<db>
XH_CHROMA_PATH=artifacts/chroma
XH_CHROMA_RAG_COLLECTION=xh_rag_documents
XH_CHROMA_ELEMENTS_COLLECTION=xh_elements
XH_ADAPTER=playwright_python
XH_PLAYWRIGHT_BROWSER=chromium
XH_PLAYWRIGHT_CHANNEL=
XH_SELENIUM_BROWSER=chrome
XH_SELENIUM_BINARY=
XH_PG_POOL_MIN=1
XH_PG_POOL_MAX=10
XH_PG_AUTO_INIT_SCHEMA=true
XH_METADATA_JSON_DIR=artifacts/metadata
XH_RAG_ENABLED=false
XH_RAG_TOP_K=5
XH_OPENAI_MODEL=gpt-4.1
XH_OPENAI_EMBED_MODEL=text-embedding-3-small
XH_STAGE_PROFILE=full
XH_STAGE_FALLBACK_ENABLED=true
XH_STAGE_METADATA_ENABLED=true
XH_STAGE_RULES_ENABLED=true
XH_STAGE_FINGERPRINT_ENABLED=true
XH_STAGE_SIGNATURE_ENABLED=true
XH_STAGE_DOM_MINING_ENABLED=true
XH_STAGE_DEFAULTS_ENABLED=true
XH_STAGE_POSITION_ENABLED=true
XH_STAGE_RAG_ENABLED=true
XH_FINGERPRINT_ENABLED=true
XH_FINGERPRINT_MIN_SCORE=0.75
XH_FINGERPRINT_ACCEPT_SCORE=0.90
XH_FINGERPRINT_CANDIDATE_LIMIT=25
XH_RETRY_ENABLED=true
XH_RETRY_MAX_ATTEMPTS=2
XH_RETRY_DELAY_MS=30
XH_RETRY_REASON_CODES=locator_error,locator_timeout,stale_element,not_visible
```

Notes:
- RAG is off by default.
- Adapter selection defaults to `playwright_python`.
- If set, `XH_OPENAI_LLM_API_KEY` and `XH_OPENAI_EMBED_API_KEY` override `OPENAI_API_KEY` for chat and embedding calls respectively.
- Set `XH_OPENAI_PROVIDER=azure` to use Azure OpenAI; then configure endpoint/api-version vars (shared or separate chat/embed).
- For Azure, deployment can be passed via `XH_AZURE_OPENAI_*_DEPLOYMENT`; if omitted, model name is used as fallback.
- Selenium validation/recovery retries include `stale_element` and `locator_timeout` transient errors by default.
- Stage profile `XH_STAGE_PROFILE=llm_only` disables all deterministic layers and leaves only RAG/LLM stage enabled.
- If `XH_PG_DSN` is set, facade uses dual metadata mode:
  Postgres primary read/write + JSON fallback/backup under `XH_METADATA_JSON_DIR`.
- Fingerprint matching is on by default and runs before signature/vector/LLM fallback.
- When `XH_RAG_ENABLED=true`, facade auto-wires LLM/embedder + ChromaDB adapters only if API keys and `XH_PG_DSN` are valid.
- Retry is lightweight: it only triggers for configured transient reason codes.
