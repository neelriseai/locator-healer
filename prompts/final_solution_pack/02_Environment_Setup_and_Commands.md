Title: Environment Setup and Commands

Objective:
- Prepare a clean machine/session to build and run XPath Healer with Playwright and Selenium integration suites.

Step 1: Optional clean reset (PowerShell)

```powershell
# optional: leave active venv
Deactivate 2>$null

# optional: remove project deps from global python (only if intentionally cleaning global site-packages)
python -m pip uninstall -y -r requirements.txt
python -m pip uninstall -y xpath-healer

# wipe local venv
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
```

Step 2: Create fresh virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev,db,llm,similarity,dom]
# or: python -m pip install -r requirements.txt
python -m playwright install chromium
```

Step 3: Quick sanity checks

```powershell
python -c "import sys, selenium; print(sys.executable); print(selenium.__version__)"
python -m pytest --version
```

Step 4: Environment variables (OpenAI provider example)

```powershell
$env:XH_ADAPTER = "playwright_python"   # or selenium_python
$env:XH_HEADLESS = "false"

$env:XH_PLAYWRIGHT_BROWSER = "chromium"
$env:XH_PLAYWRIGHT_CHANNEL = ""
$env:XH_PLAYWRIGHT_WINDOW_WIDTH = "2560"
$env:XH_PLAYWRIGHT_WINDOW_HEIGHT = "1440"

$env:XH_SELENIUM_BROWSER = "chrome"
$env:XH_SELENIUM_BINARY = ""

$env:XH_SCREENSHOT_EACH_TEST = "true"
$env:XH_SCREENSHOT_ON_FAILURE = "true"
$env:XH_SCREENSHOT_EACH_STEP = "true"
$env:XH_VIDEO_EACH_TEST = "true"
$env:XH_VIDEO_WIDTH = "1280"
$env:XH_VIDEO_HEIGHT = "720"

$env:XH_STAGE_PROFILE = "full"           # or llm_only
$env:XH_STAGE_RAG_ENABLED = "true"
$env:XH_RAG_ENABLED = "true"

$env:XH_RETRY_ENABLED = "true"
$env:XH_RETRY_MAX_ATTEMPTS = "2"
$env:XH_RETRY_DELAY_MS = "30"
$env:XH_RETRY_REASON_CODES = "locator_error,locator_timeout,stale_element,not_visible"

$env:XH_OPENAI_PROVIDER = "openai"
$env:OPENAI_API_KEY = "<real-key>"
$env:XH_OPENAI_LLM_API_KEY = "<real-key>"
$env:XH_OPENAI_EMBED_API_KEY = "<real-key>"
$env:XH_OPENAI_MODEL = "gpt-4.1"
$env:XH_OPENAI_EMBED_MODEL = "text-embedding-3-large"
$env:XH_OPENAI_EMBED_DIM = "1536"

$env:XH_PG_DSN = "postgresql://<user>:<password>@localhost:5432/<database>"
$env:XH_PG_AUTO_INIT_SCHEMA = "true"
$env:XH_PG_POOL_MIN = "1"
$env:XH_PG_POOL_MAX = "10"

$env:XH_CHROMA_PATH = "artifacts/chroma"
$env:XH_CHROMA_RAG_COLLECTION = "xh_rag_documents"
$env:XH_CHROMA_ELEMENTS_COLLECTION = "xh_elements"
```

Step 5: Environment variables (Azure provider example)

```powershell
$env:XH_OPENAI_PROVIDER = "azure"
$env:XH_RAG_ENABLED = "true"
$env:XH_STAGE_RAG_ENABLED = "true"

$env:XH_OPENAI_LLM_API_KEY = "<AZURE_OPENAI_KEY>"
$env:XH_OPENAI_EMBED_API_KEY = "<AZURE_OPENAI_KEY>"

$env:XH_AZURE_OPENAI_ENDPOINT = "https://<resource>.openai.azure.com"
$env:XH_AZURE_OPENAI_API_VERSION = "2025-01-01-preview"

$env:XH_AZURE_OPENAI_CHAT_DEPLOYMENT = "gpt-4.1"
$env:XH_AZURE_OPENAI_CHAT_API_VERSION = "2025-01-01-preview"
$env:XH_OPENAI_MODEL = "gpt-4.1"

$env:XH_AZURE_OPENAI_EMBED_DEPLOYMENT = "text-embedding-3-large"
$env:XH_AZURE_OPENAI_EMBED_API_VERSION = "2023-05-15"
$env:XH_OPENAI_EMBED_MODEL = "text-embedding-3-large"
$env:XH_OPENAI_EMBED_DIM = "1536"
```

Step 6: Validate active env values

```powershell
Get-ChildItem Env:XH_OPENAI*,Env:XH_AZURE*,Env:XH_RAG_ENABLED,Env:XH_STAGE_PROFILE,Env:XH_PG_DSN | Sort-Object Name
```

Step 7: Run tests

```powershell
python -m pytest -q tests/unit
python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json --junitxml=artifacts/reports/integration-junit.xml
python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_selenium.py --cucumberjson=artifacts/reports/cucumber-selenium.json --junitxml=artifacts/reports/integration-selenium-junit.xml
```

Expected output locations:
1. Logs: `artifacts/logs`
2. Reports: `artifacts/reports`
3. Screenshots: `artifacts/screenshots`
4. Videos: `artifacts/videos`
5. Metadata JSON: `artifacts/metadata`
6. Chroma data: `artifacts/chroma`
