# Project Index
> Maintained incrementally. AI: update this file whenever you read a source file not yet listed, or detect a fingerprint change.

---

## Metadata

```
Project Root   : (set this when deploying to a project)
Last Index Update : 2026-05-24T22:55:00Z
Indexing Mode  : INCREMENTAL
Total Files Indexed : 56
```

---

## How to Read This File

- **Fingerprint** = `size_bytes:mtime_epoch`. Recompute with:
  ```bash
  python -c "import os,sys; s=os.stat(sys.argv[1]); print(f'{s.st_size}:{int(s.st_mtime)}')" <path>
  ```
- **Status**: `CURRENT` (fingerprint verified this session) | `UNVERIFIED` (not checked yet) | `STALE` (known changed)
- **Category**: `source` | `test` | `config` | `docs` | `artifact` | `infra` | `data`

---

## File Registry

> Each row = one file. Add rows as you encounter files. Never remove rows — mark deleted files as `DELETED`.

| Path (relative to project root) | Category | Purpose (one line) | Fingerprint | Status | Last Verified |
|----------------------------------|----------|--------------------|-------------|--------|---------------|
| xpath_healer/core/strategies/bidirectional_anchor_field.py | source | Anchor-text-driven bidirectional textbox/dropdown resolver; axis_hint is soft tie-breaker only | 10784:1779520596 | CURRENT | 2026-05-23 |
| xpath_healer/core/strategies/axis_hint_field.py | source | Legacy axis-hint-dependent field resolver; kept as fallback | 3013:1775528681 | CURRENT | 2026-05-23 |
| xpath_healer/core/strategies/label_proximity_interactable.py | source | Bidirectional label-anchored resolver for button/checkbox/radio | 4942:1775528681 | CURRENT | 2026-05-23 |
| xpath_healer/core/strategies/__init__.py | source | Strategy catalog exports | 1690:1779521318 | CURRENT | 2026-05-23 |
| xpath_healer/core/strategies/base.py | source | Strategy ABC + dedupe_locators helper | 1015:1772390791 | CURRENT | 2026-05-23 |
| xpath_healer/core/models.py | source | Core dataclasses: LocatorSpec, Intent, ElementMeta, BuildInput (workflow_context), Recovered (rewrite_proposal), ... | 21199:1779555678 | CURRENT | 2026-05-23 |
| xpath_healer/api/base.py | source | BaseHealerFacade, default strategy registry, RAG bootstrap | 14339:1779521318 | CURRENT | 2026-05-23 |
| tests/unit/test_bidirectional_anchor_field.py | test | Unit tests for BidirectionalAnchorFieldStrategy | 5674:1779520653 | CURRENT | 2026-05-23 |
| xpath_healer/core/validator.py | source | Field-type and text validation, geometry checks, retryable reason codes | 22928:1779530087 | CURRENT | 2026-05-23 |
| xpath_healer/core/healing_service.py | source | Stage pipeline: fallback → workflow_replay → metadata → rules → fingerprint → page_index → signature → option_fingerprint → dom_mining → defaults → position → mcp_explore → RAG | 81602:1779555615 | CURRENT | 2026-05-23 |
| xpath_healer/core/signature.py | source | SignatureExtractor: captures stable attrs, option_set (select/radio/checkbox/input), container_lca_path | 11168:1779531651 | CURRENT | 2026-05-23 |
| xpath_healer/core/graph_container.py | source | GraphContainerGrounder: narrowest-container heuristic via single DOM evaluate | 15832:1779534694 | CURRENT | 2026-05-23 |
| xpath_healer/core/page_index.py | source | PageIndexer + weighted scorer; container_similarity now enriched with container_lca_path tokens | 36295:1779534897 | CURRENT | 2026-05-23 |
| xpath_healer/core/config.py | source | HealerConfig + StageConfig (now with option_fingerprint flag) | 10156:1779534771 | CURRENT | 2026-05-23 |
| tests/unit/test_option_fingerprint.py | test | Phase 2 tests: ElementSignature round-trip, GraphContainerGrounder, option_fingerprint stage | 12222:1779535282 | CURRENT | 2026-05-23 |
| xpath_healer/llm/__init__.py | source | Model-agnostic LLM client package exports | 970:1779536327 | CURRENT | 2026-05-23 |
| xpath_healer/llm/client.py | source | LLMClient protocol + ChatMessage/ChatResponse/ToolCall/ToolDefinition dataclasses | 1978:1779536340 | CURRENT | 2026-05-23 |
| xpath_healer/llm/openai_chat.py | source | OpenAIChatClient: tool-calling chat impl reusing existing OpenAI/Azure env conventions | 5762:1779536364 | CURRENT | 2026-05-23 |
| xpath_healer/mcp/__init__.py | source | MCP exploratory healer package exports | 1171:1779536388 | CURRENT | 2026-05-23 |
| xpath_healer/mcp/explorer.py | source | AgenticMCPExplorer + MCPExploratoryHealer protocol + agent tools (count_matches, inspect_matches, commit_locator); Phase 4a prompt enrichment with workflow_context | 17428:1779538284 | CURRENT | 2026-05-23 |
| xpath_healer/core/context.py | source | StrategyContext (now carries mcp_assist alongside rag_assist) | 2519:1779536509 | CURRENT | 2026-05-23 |
| xpath_healer/api/base.py | source | BaseHealerFacade: RAG + MCP + workflow-history + workflow-rewriter bootstrap; recover_locator, recover_workflow_step, report_step_outcome, _attach_rewrite_proposal + AutoApplyPolicy gate + PG/Json/InMem repo selection + Playwright-MCP-server selection | 37861:1779562846 | CURRENT | 2026-05-24 |
| tests/unit/test_mcp_explorer.py | test | Phase 3 tests: agent loop, tool dispatch, commit ranking, max budgets, first-time elements, both adapters, healing_service wiring | 14084:1779536763 | CURRENT | 2026-05-23 |
| xpath_healer/core/workflow.py | source | Workflow data model + 5: AutoApplyPolicy, expanded REWRITE_ACTION set, action_requires_new_step, is_supported_rewrite_action | 16104:1779562601 | CURRENT | 2026-05-24 |
| tests/unit/test_workflow_context.py | test | Phase 4a tests: WorkflowContext model, MCP prompt enrichment, recover_workflow_step, misuse warning | 12666:1779539864 | CURRENT | 2026-05-23 |
| xpath_healer/store/workflow_run_repository.py | source | Phase 4b: WorkflowRunRepository protocol + InMemory + JSON impls + safe_record_step / safe_update_step_status helpers | 9684:1779541144 | CURRENT | 2026-05-23 |
| xpath_healer/core/config.py | source | HealerConfig + StageConfig (4c: workflow_replay default True, workflow_rewrite default False) + WorkflowHistoryConfig | 12424:1779555557 | CURRENT | 2026-05-23 |
| xpath_healer/core/context.py | source | StrategyContext (mcp_assist, workflow_run_repository fields) | 2859:1779541231 | CURRENT | 2026-05-23 |
| tests/unit/test_workflow_run_history.py | test | Phase 4b: 30 tests across StepRun/WorkflowRun round-trip, repo contract (InMem + JSON), retention cap, JSON atomic write + path safety + corruption recovery, concurrent recording, safe_* helpers, facade auto-record + report_step_outcome | 15506:1779554741 | CURRENT | 2026-05-23 |
| xpath_healer/workflow/__init__.py | source | Phase 4c workflow package: AgenticWorkflowRewriter, RewriteResult, WorkflowRewriter protocol, build_default_rewrite_tools | 705:1779555688 | CURRENT | 2026-05-23 |
| xpath_healer/workflow/rewriter.py | source | Phase 4c agent loop: bounded budget, MVP actions {skip, abort}, reuses MCP _exec_count/_exec_inspect for tool dispatch | 13555:1779555740 | CURRENT | 2026-05-23 |
| tests/unit/test_workflow_replay.py | test | Phase 4c replay cache: 10 tests across skip conditions, trust tiers, ordering, dedupe, retention bound | 9068:1779557167 | CURRENT | 2026-05-23 |
| tests/unit/test_workflow_rewriter.py | test | Phase 4c: 17 tests across data model, MVP-action helper, agent loop (skip/abort/no-commit/budget/unknown-tool/prompt), Recovered.to_dict, facade post-cascade attach + exception swallowing | 14776:1779557225 | CURRENT | 2026-05-23 |
| xpath_healer/core/page_signature.py | source | Phase 5: cheap structural hash of HTML for replay-cache gating | 2215:1779562384 | CURRENT | 2026-05-24 |
| xpath_healer/store/workflow_run_pg_repository.py | source | Phase 5: PostgresWorkflowRunRepository — same protocol as InMem + JSON; indexed lookup, in-txn prune | 9138:1779562705 | CURRENT | 2026-05-24 |
| xpath_healer/mcp/playwright_mcp_explorer.py | source | Phase 5: PlaywrightMCPServerExplorer — wraps @playwright/mcp server via mcp SDK; graceful fallback when SDK/server absent | 15187:1779562823 | CURRENT | 2026-05-24 |
| adapters/appium_python/__init__.py | source | Phase 5: Appium adapter package exports | 414:1779562876 | CURRENT | 2026-05-24 |
| adapters/appium_python/adapter.py | source | Phase 5: AppiumPythonAdapter + AppiumRuntimeLocator (mobile-aware evaluate, accessibility-id mapping) | 9170:1779562918 | CURRENT | 2026-05-24 |
| adapters/appium_python/facade.py | source | Phase 5: AppiumHealerFacade pre-wires AppiumPythonAdapter | 725:1779562927 | CURRENT | 2026-05-24 |
| tests/unit/test_phase5_additions.py | test | Phase 5: 30 tests covering page_signature, expanded rewriter, AutoApplyPolicy gate, PG repo (mocked), Playwright MCP explorer (mocked), Appium adapter (fake driver) | 30535:1779563662 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/__init__.py | source | Orchestrator exports (+ CandidatePick for vision candidate-based heal per "Locator healer eyes" doc) | 1972:1779641265 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/models.py | source | Orchestrator dataclasses + 11 action constants (+ ACTION_EXTRACT, PRESS_KEY, WAIT, SCROLL, HOVER, SCREENSHOT); StepRunRecord carries visual_finding | 5907:1779618347 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/decomposer.py | source | AgenticGoalDecomposer — completeness rules, multi-page workflow guidance, search-input press-key, rich-query-over-filter, sort inference, delivery-agnostic dismissal, outline-retry-with-networkidle | 18716:1779639116 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/executor.py | source | PlaywrightActionExecutor — 11 actions; extract has LLM selector + heuristic fallback + product-href-biased auto-discover for list containers; select has native + JS + custom-dropdown click+pick fallback; extract emits _href for drill-down | 44621:1779643338 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/verifier.py | source | TieredOutcomeVerifier (auto/structural/LLM) + AgenticOutcomeVerifier; LLM emit confidence capped at 0.85 so vision can override; extract+screenshot auto-pass when exec=ok | 12734:1779642317 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/runner.py | source | WorkflowOrchestrator — per-step record + visual diagnosis + Gap #1 vision override (split threshold), Gap #2 visual recovery + candidate-based vision heal (per "Locator healer eyes"), Gap #3 vision->rewrite proposal, optional-skip short-circuit, vision-insert per-step cap, replan-on-url-change, extract auto-discover fallback | 59333:1779641327 | CURRENT | 2026-05-24 |
| tests/unit/test_orchestrator.py | test | Phase 6: 33 tests covering models, AgenticGoalDecomposer (5 cases), PlaywrightActionExecutor (6 cases), TieredOutcomeVerifier (8 cases), end-to-end WorkflowOrchestrator (8 cases) | 33102:1779614810 | CURRENT | 2026-05-24 |
| tools/run_orchestrator_demo.py | source | Phase 6 demo runner: NL goal -> agentic plan -> e2e execution against demoqa, headed, picks up .openai_key | 8318:1779615501 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/recorder.py | source | Phase 7 WorkflowRecorder: per-step screenshots or Playwright video; off/screenshots/video modes; RecordingInfo + StepSnapshot dataclasses | 8499:1779618119 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/visual.py | source | Phase 7 VisualInspector — ffmpeg frames + yt-dlp + Whisper + multimodal LLM; pick_candidate() for candidate-based vision heal per "Locator healer eyes" doc; explicit step_succeeded field in JSON schema; --zoom support; CandidatePick dataclass | 26593:1779641251 | CURRENT | 2026-05-24 |
| xpath_healer/llm/openai_chat.py | source | OpenAI tool-calling chat client + multimodal pass-through + retry-with-backoff for 429/5xx/transients (parses "try again in Xms" server hints) | 9826:1779637321 | CURRENT | 2026-05-24 |
| tests/unit/test_orchestrator_actions.py | test | 20 tests for press_key/wait/scroll/hover/screenshot/extract + extracted_data plumbing | 19727:1779616577 | CURRENT | 2026-05-24 |
| tests/unit/test_orchestrator_visual.py | test | 15 tests for VisualUsagePolicy, WorkflowRecorder (off/screenshots/video), VisualInspector (no-llm/no-frames/mock-llm/prose-wrapped JSON/exception swallow), orchestrator vision gating | 15108:1779618955 | CURRENT | 2026-05-24 |
| tools/inspect_workflow_video.py | source | Standalone CLI for VisualInspector: local video, remote URL via yt-dlp, screenshot dir, focused start/end/frames, optional transcript | 4008:1779618778 | CURRENT | 2026-05-24 |
| tools/run_flipkart_demo.py | source | Agentic e-commerce demo: NL goal "find phones under 90k + extract name/price/rating"; --record (off/screenshots/video) + --visual-policy flags wire Phase 7 vision into orchestrator | 12581:1779634349 | CURRENT | 2026-05-24 |
| tools/run_amazon_demo.py | source | Amazon drill-down workflow: search via direct URL, dismiss popups, extract first N products (name+price+_href), then per-product PDP extract (title+price+reviews) | 16862:1779642059 | CURRENT | 2026-05-24 |
| tools/run_flipkart_drill_demo.py | source | Flipkart drill-down workflow (mirror of Amazon): search via direct URL, extract N product cards, per-PDP extract title+price+reviews | 11362:1779642835 | CURRENT | 2026-05-24 |
| tests/conftest.py | test | Hermetic-env fixture + simple_context for unit tests | 2674:1779530683 | CURRENT | 2026-05-23 |
| tests/unit/test_healing_service.py | test | Healing service e2e tests (attribute reuse, robust xpath persistence) | 4036:1779530230 | CURRENT | 2026-05-23 |
| tests/unit/test_selenium_adapter.py | test | Selenium adapter e2e and validator tests | 3816:1779530237 | CURRENT | 2026-05-23 |

---

## Directory Map

> High-level map of directories. Populate as you explore.

| Directory | Role | Key Files |
|-----------|------|-----------|
| *(no entries yet)* | | |

---

## Entry Point Registry

> Files that are executable entry points (mains, CLIs, test runners, server launchers).

| File | How to Run | What It Does |
|------|-----------|--------------|
| *(no entries yet)* | | |

---

## Config Files Registry

> Config files are high-value — changes to them often invalidate many task cache entries.

| File | Format | Governs |
|------|--------|---------|
| *(no entries yet)* | | |

---

## Ignored Paths

> Paths the AI should never read or index (too large, generated, binary, sensitive).

```
# Add patterns here — one per line, glob syntax
artifacts/
*.log
*.png
*.webm
*.mp4
*.sqlite3
*.pyc
__pycache__/
.venv/
node_modules/
.git/
dist/
build/
*.lock
```

---

## Index Maintenance Log

> Record significant index updates here for auditability.

| Timestamp | Action | Details |
|-----------|--------|---------|
| 2026-05-23 | ADD | Initial entries for healing strategy chain after Phase 1 (BidirectionalAnchorFieldStrategy) |
| 2026-05-23 | ADD | Validator/healing_service/conftest entries after fixing 9 pre-existing failing tests |
| 2026-05-23 | ADD | Phase 2 entries: signature.py, graph_container.py, page_index.py, config.py, option_fingerprint tests |
| 2026-05-23 | ADD | Phase 3 entries: xpath_healer/llm package, xpath_healer/mcp package, context.py mcp_assist, api/base.py mcp wiring, mcp tests |
| 2026-05-23 | ADD | Phase 4a entries: core/workflow.py, BuildInput.workflow_context, MCP prompt enrichment, recover_workflow_step + misuse warning, workflow_context tests |
| 2026-05-23 | ADD | Phase 4b entries: store/workflow_run_repository.py, WorkflowHistoryConfig, context.workflow_run_repository, BaseHealerFacade auto-record + report_step_outcome, workflow_run_history tests |
| 2026-05-23 | ADD | Phase 4c entries: workflow/ package (rewriter), WorkflowRewriteProposal + Recovered.rewrite_proposal, replay stage in healing_service, replay + rewriter tests |
| 2026-05-24 | ADD | Phase 5 entries: page_signature, PG workflow repo, PlaywrightMCPServerExplorer, AppiumAdapter + facade, AutoApplyPolicy gate, expanded rewrite actions, phase5 tests |
| 2026-05-24 | ADD | Phase 6 entries: orchestrator package (models, decomposer, executor, verifier, runner), 33 orchestrator tests, demo runner; e2e demoqa text-box: 5 steps via deterministic heals + 2 LLM calls total |
| 2026-05-24 | EXPAND | Action vocabulary: extract, press_key, wait, scroll, hover, screenshot; 20 new action tests; Flipkart demo runner |
| 2026-05-24 | ADD | Phase 7 video-as-vision: WorkflowRecorder, VisualInspector (ffmpeg/yt-dlp/Whisper graceful), VisualUsagePolicy enum, multimodal OpenAI chat, orchestrator policy-gated diagnosis, inspect_workflow_video CLI, 15 visual tests |
| 2026-05-24 | EXPAND | run_flipkart_demo --record + --visual-policy flags wire recorder + VisualInspector into orchestrator; e2e proof: vision tier reversed false-negative text-tier verdict on submit_search step (ok=True conf=1.0); standalone CLI also picked phone grid frame from same screenshots |
| 2026-05-24 | DEEPEN | Vision integration round 2: Gap #1 (vision override of text-tier false-negative — threshold split visual_override_threshold=0.8 + visual_block_override_threshold=0.95); Gap #2 (visual recovery for heal-failed steps); Gap #3 (vision finding -> WorkflowRewriteProposal with insert_before/abort/skip); Gap #4 (--zoom flag + targeted before/after diagnosis question); +13 unit tests |
| 2026-05-24 | DEEPEN | Robustness: OpenAI 429/5xx retry-with-backoff (parses server's "try again in Xms"); extract emits _href for drill-down; extract auto-discover via JS repeating-structure scan with product-href bias (Amazon /dp, Flipkart /p/itm); custom-dropdown _select fallback (click + open + click option); optional-step heal-miss short-circuit; per-step vision-insert cap; replan-on-url-change after major page navigation; verifier short-circuits extract+screenshot as read-only |
| 2026-05-24 | ADD | Candidate-based vision heal per "Locator healer eyes" doc: VisualInspector.pick_candidate() + CandidatePick dataclass + JS DOM-candidate extraction (40 clickable elements with bbox + stable selectors) + runner wiring as new strategy after text-tier cascade fails. Vision now picks DOM nodes (not coords) for clicks |
| 2026-05-24 | ADD | run_amazon_demo (drill-down workflow): direct-URL search + dismiss + extract first N products + per-product PDP extract; run_flipkart_drill_demo (mirror); both demonstrate full end-to-end agentic workflow with all 3 healing layers + Phase 7 vision; Flipkart drill 3/3 success returning real product title + price + reviews |
| 2026-05-24 | VALIDATE | 3-layer feature regression PASSED on all 3 layers (was: L2 failing on OpenAI 429; now retry-fix made L2 pass). 271 unit tests passing across orchestrator + vision + executor + decomposer + verifier |

---

## Template: Adding a File Entry

Copy this row format when adding a new file:

```
| path/to/file.py | source | Brief one-line purpose | 4821:1712345678 | CURRENT | 2026-04-07 |
```

**Rules:**
- Path must be relative to project root
- Purpose must be one line, plain English, no jargon
- Fingerprint format: `size_bytes:mtime_epoch` (integer seconds since Unix epoch)
- Status starts as `CURRENT` when you just read/verified it
- Last Verified = date you verified the fingerprint (YYYY-MM-DD)
