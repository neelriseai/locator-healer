# XPath Healer

A locator-healing + workflow-orchestration engine for browser automation.
When a Playwright/Selenium selector breaks against a moving UI, this
library finds the new element — without you rewriting the test. When
you want to drive an end-to-end browser flow from a natural-language
goal, the same engine plans + executes + verifies + recovers, with
measured cost and a deterministic-first cost model.

```
+----------------------+      +--------------------------+
|  Your test / agent   |----> |  XPathHealer Facade      |
+----------------------+      |  recover_locator(...)    |
                              |  recover_workflow_step() |
                              |  + WorkflowOrchestrator  |
                              +-----------+--------------+
                                          |
   +--------------------------------------+--------------------------------------+
   |                          Heal cascade (deterministic-first)                  |
   |                                                                              |
   |  fallback  ->  metadata cache  ->  rules    ->  fingerprint   ->  page-index |
   |     ->  signature   ->  option-fingerprint  ->  dom-mining   ->  defaults    |
   |     ->  position    ->  MCP agent (LLM)      ->  RAG (LLM + Chroma)          |
   |                          + vision candidate-pick (Phase 7)                   |
   +------------------------------------------------------------------------------+
                                          |
                              +-----------+--------------+
                              |  Adapters (pluggable)    |
                              |  - Playwright (async)    |
                              |  - Selenium (sync)       |
                              +--------------------------+
```

**Design rule**: cheap deterministic strategies are tried first; LLM and
vision are last resorts. A single locator heal typically costs 0 LLM
calls; a fresh 5-step workflow runs end-to-end in ~2 LLM calls thanks
to tiered verification.

---

## What's in the box

| Capability | What it is | Where it lives | Evidence |
|---|---|---|---|
| **Locator heal cascade** | 12 strategies, deterministic-first, returns a healed `LocatorSpec` for a known-broken xpath | `xpath_healer/core/strategies/*` | `tools/precision_corpus.py` → strict node-identity precision **L1=5/5 (100%)** |
| **Workflow orchestrator** | NL goal → planned steps → execute + heal + verify, with replan and auto-recovery | `xpath_healer/orchestrator/runner.py` | Flipkart/Amazon drill demos extract real product data |
| **Action executor** | 12 actions: navigate, fill, click, select, verify, extract, extract_record, press_key, wait, scroll, hover, screenshot | `xpath_healer/orchestrator/executor.py` | 20+ executor unit tests |
| **Outcome verifier (tiered)** | auto / structural / LLM tiers — keeps verification cost flat across workflow length | `xpath_healer/orchestrator/verifier.py` | 5-step workflow typically uses 0–1 LLM verifications |
| **Vision tier (Phase 7)** | Vision LLM diagnoses failures, picks DOM candidates from screenshots, overrides text-tier false-negatives, proposes dismiss-modal / abort | `xpath_healer/orchestrator/visual.py` + `runner.py` | Live Flipkart proof: `visual_candidate_pick` strategy fires when cascade disabled |
| **Telemetry + SLO** | Per-run LLM calls / tokens / vision calls / duration / heal-strategy counts; SLO `.check()` returns ok/observed/limit | `xpath_healer/orchestrator/telemetry.py` | `~9.4k tokens, ~6s per Flipkart drill` |
| **Goal-vs-action contract** | Demotes `status=success` → `failed` when a goal demands an action but only verify-only steps ran (catches false-success on empty/captcha pages) | `runner.py:_goal_action_unmet` | `tools/adversarial_browser.py` 4/4 PASS |
| **Page-state observer** | Structured JSON (url, page_type, forms, buttons, errors, modals, next_possible_actions) consumed by the decomposer | `xpath_healer/orchestrator/page_state.py` | `_OBSERVE_JS` cap-respecting scan |
| **Workflow run history** | InMemory / JSON-file / Postgres backends; auto-record + replay-cache for repeat runs | `xpath_healer/store/*` | 30 unit tests across backends |
| **Recorder + standalone vision CLI** | Per-step screenshots or `.webm` video; `tools/inspect_workflow_video.py` for ad-hoc debugging | `xpath_healer/orchestrator/recorder.py` | yt-dlp + ffmpeg + native captions + Whisper transcript |
| **MCP exploratory healer** | Bounded LLM agent loop with `count_matches` / `inspect_matches` / `commit_locator` tools | `xpath_healer/mcp/explorer.py` | Layer-2 of the 3-layer regression |
| **RAG retrieval** | Postgres metadata + Chroma vector store; suggests historical locators by intent similarity | `xpath_healer/rag/*` | Layer-3 of the 3-layer regression |
| **Workflow rewriter** | When a step is unfixable, emits skip / abort / insert_before / replace proposals (with `AutoApplyPolicy` safety gate) | `xpath_healer/workflow/rewriter.py` | Vision integration synthesises these locally too |

---

## Quick install

```bash
# editable + all extras (recommended for development)
python -m pip install -e ".[dev,similarity,dom,db,llm]"
playwright install chromium

# minimal runtime (heal-cascade only, no LLM, no RAG)
python -m pip install -e .
playwright install chromium
```

Optional extras:

| Extra | What it pulls in | When you need it |
|---|---|---|
| `similarity` | `rapidfuzz` | Fingerprint similarity scoring |
| `dom` | `beautifulsoup4`, `lxml` | DOM-mining strategies |
| `db` | `asyncpg`, `chromadb` | Postgres workflow-run repo + RAG vector store |
| `llm` | `openai>=1.66` | MCP agent, vision tier, RAG embeddings |
| `dev` | `pytest`, `pytest-asyncio`, `pytest-bdd` | Running the test + integration suites |

---

## Quick start — library usage

### Heal a single broken locator

```python
import asyncio
from playwright.async_api import async_playwright
from xpath_healer.api.facade import XPathHealerFacade
from xpath_healer.core.models import LocatorSpec

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://demoqa.com/text-box")

        facade = XPathHealerFacade()  # env-driven config

        recovered = await facade.recover_locator(
            page=page,
            app_id="my-app",
            page_name="signup",
            element_name="email",
            field_type="textbox",
            fallback=LocatorSpec(kind="xpath", value="//input[@id='broken-id']"),
            vars={"label": "Email"},
        )

        if recovered.status == "success":
            # Drive it with the framework you already use:
            await recovered.playwright_locator.fill("alice@example.com")

        await browser.close()

asyncio.run(main())
```

### Run a full workflow from a natural-language goal

```python
import asyncio, os
from playwright.async_api import async_playwright
from xpath_healer.api.facade import XPathHealerFacade
from xpath_healer.llm.openai_chat import OpenAIChatClient
from xpath_healer.orchestrator import (
    AgenticGoalDecomposer, AgenticOutcomeVerifier, PlaywrightActionExecutor,
    TelemetryCounter, TelemetryLLMClient, TieredOutcomeVerifier,
    WorkflowGoal, WorkflowOrchestrator,
)

async def main():
    llm = OpenAIChatClient(api_key=os.environ["OPENAI_API_KEY"], model="gpt-4o-mini")
    counter = TelemetryCounter()
    wrapped_llm = TelemetryLLMClient(llm, counter)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()

        facade = XPathHealerFacade()
        orch = WorkflowOrchestrator(
            facade=facade,
            decomposer=AgenticGoalDecomposer(wrapped_llm),
            executor=PlaywrightActionExecutor(llm_for_extract=wrapped_llm),
            verifier=TieredOutcomeVerifier(llm_verifier=AgenticOutcomeVerifier(wrapped_llm)),
            telemetry=counter,
        )

        goal = WorkflowGoal(
            text="On the search results page, extract the first 5 product titles and prices.",
            start_url="https://www.flipkart.com/search?q=mobile+phones+under+50000",
        )
        result = await orch.run(page=page, goal=goal)
        print(result.status, result.extracted_data)
        print(result.metadata["telemetry"])  # llm_calls, tokens, vision_calls, ...

        await browser.close()

asyncio.run(main())
```

---

## Demo runners (out-of-the-box)

Every demo prints a step-by-step trace + per-run telemetry. Most write
a JSON artifact under `artifacts/reports/`.

| Tool | What it does | Command |
|---|---|---|
| `tools/run_orchestrator_demo.py` | Phase-6 demo: fills the demoqa text-box form via NL goal | `python tools/run_orchestrator_demo.py --headed` |
| `tools/run_flipkart_demo.py` | Searches Flipkart, extracts product cards; supports `--record` + `--visual-policy` | `python tools/run_flipkart_demo.py --headed --record screenshots --visual-policy on_failure` |
| `tools/run_amazon_demo.py` | Same but for Amazon: phase-1 list extraction + per-product PDP drill via `extract_record` | `python tools/run_amazon_demo.py --headed --limit 3 --max-price 50000` |
| `tools/run_flipkart_drill_demo.py` | Flipkart drill-down with telemetry + SLO check + per-PDP `extract_record` | `python tools/run_flipkart_drill_demo.py --headed --limit 3 --max-price 50000 --record screenshots --visual-policy on_failure` |
| `tools/run_all_layers_headed.py` | Runs the demoqa feature regression three times — once per layer (deterministic / MCP-agentic / RAG) — to prove each layer can stand alone | `python tools/run_all_layers_headed.py` |
| `tools/inspect_workflow_video.py` | Standalone vision CLI: ask a focused question about a recorded `.webm` / screenshot set | `python tools/inspect_workflow_video.py --video artifacts/recordings/videos/foo.webm --question "Did the search succeed?" --start 5 --end 15` |
| `tools/force_vision_candidate_heal.py` | Disables every deterministic stage so the candidate-based vision heal is the only path to find an element | `python tools/force_vision_candidate_heal.py --headed` |
| `tools/precision_corpus.py` | Ground-truth precision harness — strict node-identity (Playwright handles + `el.isSameNode`); runs per layer | `python tools/precision_corpus.py --layer all` |
| `tools/adversarial_browser.py` | Real-browser robustness harness — loads `tests/fixtures/adversarial/*.html` and asserts graceful behavior | `python tools/adversarial_browser.py` |
| `tools/concurrent_stress.py` | Real concurrent stress — N Playwright workers sharing ONE facade; verifies node-correct heals + isolated counters | `python tools/concurrent_stress.py --workers 10` |
| `tools/report_heal_metrics.py` | Aggregates per-layer `healing-calls.jsonl` artifacts into per-strategy success metrics | `python tools/report_heal_metrics.py` |
| `tools/reset_db_and_chroma.ps1` | Wipes Postgres workflow tables + Chroma collections (Windows PowerShell) | `pwsh tools/reset_db_and_chroma.ps1` |
| `tools/rag_db_stats.py` | Counts embeddings + metadata rows so you can confirm RAG warmup state | `python tools/rag_db_stats.py` |

---

## REST API service

The thin FastAPI wrapper exposes the same facade over HTTP:

```bash
uvicorn service.main:app --reload --port 8000
```

POST a heal request:

```bash
curl -X POST http://localhost:8000/heal \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "demo",
    "page_name": "login",
    "element_name": "submit",
    "field_type": "button",
    "fallback_xpath": "//button[@id=\"broken\"]",
    "vars": {"label": "Submit"}
  }'
```

(The page is captured server-side via the configured adapter; see
`service/main.py` for the exact request schema.)

---

## Distribution — building a wheel ("packaged jar")

Python's equivalent of a fat jar is a **wheel** (`.whl`) — a single
installable archive a downstream team can `pip install`.

```bash
python -m pip install build
python -m build           # produces dist/xpath_healer-0.1.0-py3-none-any.whl + dist/*.tar.gz
```

Distribute the `.whl`. Consumers install it like:

```bash
pip install xpath_healer-0.1.0-py3-none-any.whl[llm,db]
playwright install chromium
```

…and import the public API:

```python
from xpath_healer.api.facade import XPathHealerFacade
from xpath_healer.core.models import LocatorSpec
from xpath_healer.orchestrator import (
    WorkflowOrchestrator, AgenticGoalDecomposer, PlaywrightActionExecutor,
    TieredOutcomeVerifier, AgenticOutcomeVerifier, WorkflowGoal,
    TelemetryCounter, TelemetryLLMClient, TelemetryVisualInspector,
    VisualInspector, WorkflowRecorder, SLO, PageStateObserver,
)
```

**Public surface area worth knowing:**

| Symbol | Purpose |
|---|---|
| `XPathHealerFacade` | Single entry point for `recover_locator()` + `recover_workflow_step()` + `report_step_outcome()` — env-driven config |
| `WorkflowOrchestrator` | Drives a full NL-goal → done loop with heal + execute + verify + replan |
| `PlaywrightActionExecutor` | 12-action executor; pass an `llm_for_extract` to enable LLM-backed extract |
| `AgenticGoalDecomposer` | LLM planner; consumes `PageStateObserver` JSON for richer planning |
| `TieredOutcomeVerifier` + `AgenticOutcomeVerifier` | auto / structural / LLM verification tiers |
| `VisualInspector` (+ `WorkflowRecorder`) | Phase-7 vision: candidate-pick, override, recovery, dismiss-modal proposal |
| `TelemetryCounter` / `TelemetryLLMClient` / `TelemetryVisualInspector` | Wrap any LLM/inspector to count calls + tokens + time |
| `SLO` | Per-run service-level objectives with `.check()` |
| `PageStateObserver` | Structured page-state JSON (forms / buttons / modals / errors / next-actions) |

---

## Configuration — environment variables

Heal cascade + adapters:

| Var | Default | Purpose |
|---|---|---|
| `XH_ADAPTER` | `playwright_python` | `playwright_python` or `selenium_python` |
| `XH_PLAYWRIGHT_BROWSER` | `chromium` | Playwright engine: `chromium` / `chrome` / `edge` / `firefox` / `webkit` |
| `XH_PLAYWRIGHT_CHANNEL` | (none) | Channel override: `chrome` / `msedge` / ... |
| `XH_SELENIUM_BROWSER` | `chrome` | Selenium driver: `chrome` / `chromium` / `edge` / `firefox` |

Stage gates (turn each layer on/off — used by the 3-layer regression):

| Var | Stage |
|---|---|
| `XH_STAGE_FALLBACK_ENABLED` | Try the caller's original xpath first |
| `XH_STAGE_METADATA_ENABLED` | Reuse last-good locator from metadata store |
| `XH_STAGE_RULES_ENABLED` | Field-type rule strategies (button text, bidirectional anchor, ...) |
| `XH_STAGE_FINGERPRINT_ENABLED` | Attribute-similarity scoring vs stored ElementMeta |
| `XH_STAGE_PAGE_INDEX_ENABLED` | Whole-page ranked candidate selection |
| `XH_STAGE_SIGNATURE_ENABLED` | Sample-page signature gating for replay |
| `XH_STAGE_OPTION_FINGERPRINT_ENABLED` | Select/radio option-set fingerprint |
| `XH_STAGE_DOM_MINING_ENABLED` | First-run DOM scan for label-anchored candidates |
| `XH_STAGE_DEFAULTS_ENABLED` | Tag/role/type defaults |
| `XH_STAGE_POSITION_ENABLED` | Last-resort coordinate-based fallback |
| `XH_STAGE_MCP_EXPLORE_ENABLED` | LLM agent loop (`mcp_explore` strategy) |
| `XH_STAGE_RAG_ENABLED` | RAG suggestion via Chroma similarity |
| `XH_STAGE_PROFILE` | Shorthand: `full` / `llm_only` / `deterministic_only` |

Workflow / orchestrator / vision:

| Var | Purpose |
|---|---|
| `OPENAI_API_KEY` | Required for any LLM-backed stage / orchestrator path. The orchestrator demos also pick up a local `.openai_key` file (gitignored). |
| `XH_OPENAI_MODEL` | Default `gpt-4.1`. Demos use `gpt-4o-mini` for cost. |
| `XH_OPENAI_EMBED_MODEL` | Default `text-embedding-3-small` |
| `XH_OPENAI_PROVIDER` | `openai` (default) or `azure` |
| `XH_AZURE_OPENAI_*` | Endpoint / api-version / deployment for Azure (chat + embed can be split) |
| `XH_MCP_MAX_ROUNDS`, `XH_MCP_MAX_TOOL_CALLS`, `XH_MCP_MAX_COMMITS` | MCP agent budgets |

Storage:

| Var | Purpose |
|---|---|
| `XH_PG_DSN` | Postgres DSN for workflow-run history + dual metadata. Unset → JSON-file only. |
| `XH_PG_AUTO_INIT_SCHEMA` | `true` lets the facade create the tables on first connect |
| `XH_METADATA_JSON_DIR` | Where the JSON metadata repo lives (default `artifacts/metadata`) |
| `XH_CHROMA_PATH` | Chroma storage path (default `artifacts/chroma`) |
| `XH_CHROMA_RAG_COLLECTION`, `XH_CHROMA_ELEMENTS_COLLECTION` | Collection names |
| `XH_WORKFLOW_HISTORY_ENABLED` | Toggle workflow-run recording |

Reporting / artifacts:

| Var | Purpose |
|---|---|
| `XH_HEADLESS` | `false` for headed integration runs |
| `XH_REPORTS_DIR`, `XH_LOGS_DIR`, `XH_SCREENSHOTS_DIR`, `XH_VIDEOS_DIR` | Override artifact roots per run |
| `XH_HEALING_CALLS_REPORT` | Path to write per-heal jsonl (consumed by `report_heal_metrics.py`) |

---

## Tests + validation harnesses

| Suite | What it covers | Run |
|---|---|---|
| Unit tests | Healers, orchestrator, executor, verifier, vision, telemetry, SLO, page-state, recorder | `python -m pytest tests/unit -q` |
| Integration (BDD) | 3 demoqa scenarios via real Playwright; gated by stage env vars | `python -m pytest tests/integration -q` |
| 3-layer regression | Same integration tests run once per layer to prove each can stand alone | `python tools/run_all_layers_headed.py` |
| Precision corpus | Strict node-identity precision per layer | `python tools/precision_corpus.py --layer all` |
| Adversarial harness | Empty / JS-shell / captcha / huge-page real HTML fixtures | `python tools/adversarial_browser.py` |
| Concurrent stress | N Playwright workers sharing one facade | `python tools/concurrent_stress.py --workers 10` |
| Heal metrics | Per-strategy success rate from existing artifacts | `python tools/report_heal_metrics.py` |

---

## Why use this — concrete benefits

1. **Cost-controlled by design.** Deterministic-first means most heals cost zero LLM calls. A full multi-page e-commerce drill workflow runs at ~9.4k tokens (~6s). Telemetry numbers are in `OrchestrationResult.metadata["telemetry"]`.
2. **Resilient to UI drift.** When `<button>Submit</button>` becomes `<button>Continue</button>`, the bidirectional-anchor and MCP strategies still find it. Validated end-to-end on demoqa + Flipkart + Amazon.
3. **Adapter-agnostic heal cascade.** Same `recover_locator()` API works with Playwright and Selenium today; the contract is `AutomationAdapter` (any test framework can plug in).
4. **Workflow orchestration with measurable accuracy.** Decomposer + executor + tiered verifier + heal cascade + vision tier + telemetry + SLO. Goal-vs-action contract catches the "looks successful but did nothing" failure mode.
5. **Vision as a fallback, not a default.** Vision tier fires `on_failure` (or `on_ambiguous`); never burns tokens when the deterministic cascade is working. Candidate-based heal (per the "Locator healer eyes" design) grounds vision in real DOM nodes rather than raw pixel coordinates.
6. **Self-healing workflow execution.** Vision findings synthesise `WorkflowRewriteProposal`s — `insert_before(dismiss_modal)`, `abort(captcha)`, `skip(optional)` — so the orchestrator recovers from blockers without manual intervention. Per-step caps prevent cascades.
7. **Replay caches.** Workflow-run history (InMemory / JSON / Postgres) lets repeat runs reuse last-good locators for free. RAG layer also suggests historical locators by intent similarity.
8. **Observability.** Per-run telemetry (LLM calls / tokens / vision calls / duration / heal-strategy distribution / step durations) is structured, queryable, and free.
9. **Tested deeply.** 310 unit tests including concurrent isolation, long-workflow stress, adversarial real-HTML fixtures, 429-retry, replan-on-URL-change, vision override / recovery / candidate-pick. Real-browser harnesses validate strict precision (`isSameNode` checks) and concurrent safety with shared facade.

---

## Project layout

```
xpath_healer/
  api/facade.py            # XPathHealerFacade — single public entry point
  core/                    # heal cascade: strategies, validator, healing service
    strategies/            # rule / fingerprint / page-index / signature / dom-mining / ...
  llm/                     # provider-agnostic chat client (OpenAI + Azure) with retry-with-backoff
  mcp/                     # exploratory MCP agent (count_matches / inspect_matches / commit_locator)
  rag/                     # embeddings + Chroma + LLM suggestion
  orchestrator/
    decomposer.py          # NL goal -> WorkflowStep[]
    executor.py            # 12 actions, custom-dropdown fallback, quality-guarded extract_record
    verifier.py            # auto / structural / LLM tiers
    runner.py              # WorkflowOrchestrator — heal + execute + verify + replan + vision
    visual.py              # VisualInspector + CandidatePick
    recorder.py            # per-step screenshots or .webm
    page_state.py          # PageStateObserver
    telemetry.py           # TelemetryCounter, wrappers, SLO
  store/                   # workflow run history backends (InMemory / JSON / Postgres)
  workflow/                # WorkflowRewriteProposal + agentic rewriter
adapters/
  playwright_python/       # facade + locator wrapper
  selenium_python/         # facade + locator wrapper
service/main.py            # FastAPI wrapper
tools/                     # demo runners + validation harnesses (see table above)
tests/
  unit/                    # 310 unit tests
  integration/             # demoqa BDD scenarios
  fixtures/adversarial/    # local HTML for the adversarial harness
ai-efficiency-pack/        # PROJECT_INDEX / SYMBOL_INDEX / TASK_CACHE / DEPENDENCY_GRAPH
```

---

## Status / health snapshot

- **310 unit tests passing** (`pytest tests/unit -q`)
- **3-layer feature regression PASS / PASS / PASS** (deterministic / MCP / RAG against demoqa)
- **Strict precision corpus**: deterministic 5/5 + MCP 5/5 (RAG cold-start 0/5 by design — needs prior history)
- **Adversarial harness**: 4/4 — empty page, JS-shell late mount, captcha wall, huge page
- **Concurrent stress**: 10 workers / shared facade / 10 node-correct + 10 isolated counters
- **Cost benchmark (Flipkart drill workflow, gpt-4o-mini)**: ~9.4k tokens, ~6s per drill, SLO PASS

---

## License

Proprietary. See `pyproject.toml`.
