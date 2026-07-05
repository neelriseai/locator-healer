# Project Index
> Maintained incrementally. AI: update this file whenever you read a source file not yet listed, or detect a fingerprint change.

---

## Metadata

```
Project Root   : (set this when deploying to a project)
Last Index Update : 2026-05-26T11:30:00Z
Indexing Mode  : INCREMENTAL
Total Files Indexed : 65
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
| xpath_healer/orchestrator/__init__.py | source | Orchestrator exports (+ CandidatePick, PageStateObserver) | 2064:1779688820 | CURRENT | 2026-05-25 |
| xpath_healer/orchestrator/models.py | source | Orchestrator dataclasses + 11 action constants; StepRunRecord carries visual_finding | 5907:1779618347 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/decomposer.py | source | AgenticGoalDecomposer — completeness rules, multi-page guidance, search-input press-key, rich-query-over-filter, sort inference, delivery-agnostic dismissal, outline-retry, PAGE_STATE_FIRST rule (consumes PageStateObserver JSON for richer planning) | 20872:1779688858 | CURRENT | 2026-05-25 |
| xpath_healer/orchestrator/executor.py | source | PlaywrightActionExecutor — 11 actions; _click upgraded with scroll-into-view + native + JS-with-elementFromPoint overlay detection (per "Locator healer eyes" §11/§12); extract LLM + heuristic + product-href auto-discover; _select native + JS + custom-dropdown click+pick; extract emits _href | 47368:1779688693 | CURRENT | 2026-05-25 |
| xpath_healer/orchestrator/verifier.py | source | TieredOutcomeVerifier (auto/structural/LLM); LLM verifier confidence capped at 0.85; extract+screenshot auto-pass when exec=ok | 12734:1779642317 | CURRENT | 2026-05-24 |
| xpath_healer/orchestrator/runner.py | source | WorkflowOrchestrator — visual diagnosis + vision override (split thresholds), visual recovery + candidate-based heal (merges DOM + a11y candidates), vision->rewrite proposal, optional-skip, vision-insert per-step cap, replan-on-url-change, extract auto-discover, goal-vs-action contract (status=failed when goal demands a real action but only verify/skipped steps ran) | 72202:1779731933 | CURRENT | 2026-05-25 |
| xpath_healer/orchestrator/page_state.py | source | PageStateObserver: structured page-state JSON (url, title, viewport, page_type, forms[fields], buttons, errors, modals, tables, next_possible_actions) per "Locator healer eyes" §3/§8; consumed by decomposer for richer planning input | 11482:1779688794 | CURRENT | 2026-05-25 |
| xpath_healer/orchestrator/telemetry.py | source | Telemetry harness: TelemetryCounter (per-run llm_calls/tokens/vision/duration/heal-strategy counts + reset()) + TelemetryLLMClient + TelemetryVisualInspector wrappers; SLO dataclass with check() returning ok/observed/limit per target; stamped into OrchestrationResult.metadata.telemetry on every run incl. failures | 8908:1779724878 | CURRENT | 2026-05-25 |
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
| tools/run_flipkart_drill_demo.py | source | Flipkart drill-down workflow (mirror of Amazon): direct-URL search, extract list, per-PDP extract_record (title+price+variant+reviews), telemetry per run, SLO check pass/fail | 13452:1779724579 | CURRENT | 2026-05-25 |
| tools/force_vision_candidate_heal.py | source | P2 validation harness: disables every deterministic heal stage so the only path to heal a click is the candidate-based vision heal; live Flipkart proof that visual_candidate_pick fires + drives a real click | 7281:1779724467 | CURRENT | 2026-05-25 |
| tools/report_heal_metrics.py | source | Precision/recall harness — consumes per-layer artifacts/reports/layer*/healing-calls.jsonl, aggregates per-strategy success rate + score stats; emits artifacts/reports/heal_metrics.json. Turns "all layers pass" into a quantitative report | 6062:1779725621 | CURRENT | 2026-05-25 |
| tools/precision_corpus.py | source | Ground-truth strict-precision harness: corpus of demoqa scenarios w/ broken fallback xpath + known-correct CSS; per layer, heals via cascade + resolves both healed and ground-truth as Playwright handles + asserts node identity via el.isSameNode(). Closes the prior "status=success = correct" loophole. L1=5/5, L2=5/5 strict precision | 18999:1779727156 | CURRENT | 2026-05-25 |
| tools/adversarial_browser.py | source | Real-browser adversarial harness — loads local HTML fixtures (empty/JS-shell/captcha/huge) into Playwright + runs the orchestrator + asserts the contract (fails_gracefully / succeeds / fails_or_aborts / succeeds_within_slo). Surfaced + fixed the goal-vs-action bug. 4/4 cases PASS | 10746:1779729939 | CURRENT | 2026-05-25 |
| tools/concurrent_stress.py | source | Real concurrent stress — N Playwright workers (each its own browser context + counter) sharing ONE XPathHealerFacade; verifies (a) every worker heals correctly via node-identity check (b) telemetry counters stay isolated. Validated 5 + 10 workers, all PASS | 8039:1779732008 | CURRENT | 2026-05-25 |
| tests/fixtures/adversarial/empty.html | data | Empty body — verifies graceful handling of pages with no interactable elements | 79:1779727284 | CURRENT | 2026-05-25 |
| tests/fixtures/adversarial/js_shell.html | data | SPA shell that mounts content 1.5s after load — verifies the decomposer's networkidle-retry path | 624:1779727292 | CURRENT | 2026-05-25 |
| tests/fixtures/adversarial/captcha_wall.html | data | Fake Cloudflare-style verify-human page — verifies the orchestrator aborts rather than spins | 1007:1779727301 | CURRENT | 2026-05-25 |
| tests/fixtures/adversarial/huge_page.html | data | 3000+ filler nodes around the real button — verifies outline + candidate extraction don't blow up | 781:1779727310 | CURRENT | 2026-05-25 |
| README.md | docs | Comprehensive project README — architecture overview, capabilities matrix, install + library usage + demo runners + REST API + wheel-distribution guide + env-var reference + tests/harnesses + benefits + project layout + health snapshot | 22406:1779749291 | CURRENT | 2026-05-26 |
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
| 2026-05-25 | DEEPEN | "Are we deeply iterating?" P1-P4 priority loop: P1 Amazon re-validation (4 rounds, max-greedy→frequency-with-EMI-filter price heuristic; prices NOW match seed exactly: ₹15,999/₹59,900/₹48,950); P2 force vision-candidate-heal in LIVE Flipkart with cascade fully disabled (visual_candidate_pick fired, exec=ok, 2 vision_calls, 5k tokens, 24s); P3a 2 tests for OpenAI 429 retry-with-backoff; P3b 2 tests for replan-on-URL-change incl. empty-baseline bug surfaced + fixed; P4 SLO dataclass + check() + 4 tests + per-run telemetry reset + wired into Flipkart demo (final round 11: phase1=success drill_ok=3/3 slo=PASS on all 4 runs). 300 unit tests pass (+8 new) |
| 2026-05-25 | DEEPEN | Robustness round 2: concurrent run isolation (2 tests prove separate counters don't leak + same orchestrator resets between sequential runs); long workflow stress (2 tests: 50-step success + 50-step fail-fast); adversarial inputs (3 tests: empty page / JS-shell-no-DOM / captcha → graceful abort proposal); precision/recall harness consuming existing healing-calls.jsonl artifacts → measurable evidence: 33/33 heals = 100% precision across L1 (5 deterministic strategies) + L2 (mcp_explore) + L3 (rag_suggest). Skipped Selenium-adapter-in-orchestrator per "don't introduce new issues" guidance — heal cascade already works with Selenium, only the workflow executor is Playwright-only and adding parallel Selenium executor is substantial work for low immediate value. 307 unit tests pass (+7 new) |
| 2026-05-25 | DEEPEN | Robustness round 3 (closing the "shallow" gaps from self-audit): (1) precision_corpus.py — STRICT node-identity precision harness using Playwright element handles + isSameNode; L1=5/5 + L2=5/5 strict precision (vs prior loose "status=success" metric). (2) adversarial_browser.py — real HTML fixtures rendered in a real browser (vs prior monkeypatched mocks); surfaced + fixed the GOAL-VS-ACTION BUG (orchestrator was returning status=success when a goal demanded "click X" but only verify-only steps ran); fixed with primary-intent detection in WorkflowOrchestrator._goal_action_unmet + _is_verification_only_goal; 4/4 adversarial cases now PASS. (3) concurrent_stress.py — N real Playwright workers sharing ONE facade; validated 5 + 10 workers, every heal node-correct, every counter isolated. 310 unit tests pass (+3 new locking goal-vs-action contract). 3-layer feature regression still PASS |
| 2026-05-26 | DOCS | Rewrote README.md from 128-line minimal version to 402-line comprehensive guide. Covers: architecture overview with ASCII diagram, capabilities matrix with evidence pointers, install + extras, library quick-start (heal-only + workflow orchestrator), demo-runner catalog (13 tools), REST API, wheel packaging guide, full env-var reference, test/harness catalog, benefits, project layout, health snapshot (310 tests / L1+L2 = 5/5 strict precision / adversarial 4/4 / concurrent 10/10) |
| 2026-05-25 | ADD | "Locator healer eyes" round 2 — implemented 3 high-leverage doc changes (skipped 4 duplicate-path proposals): (1) PageStateObserver: structured page-state JSON (forms/buttons/modals/errors/next_actions) fed into decomposer prompt with PAGE_STATE_FIRST rule; (2) Accessibility-tree candidates (page.accessibility.snapshot) merged into visual-candidate heal, deduped against DOM-scan; (3) _click upgraded — scrollIntoViewIfNeeded → native → elementFromPoint overlay detect → JS-click. +5 unit tests (276 pass). Flipkart drill 3/3 still success; 3-layer regression all PASS |
| 2026-05-25 | DEEPEN | Self-audit round 3: implemented all 6 gap-list items from "honest residuals" analysis. (#6) Budget-exhaustion tests proving max_recovery_inserts=0 + max_replans=0 + vision-insert per-step cap. (#3) Overlay-detection test exercising scroll → native → elementFromPoint → JS-click. (#1) Force-exercise candidate-heal test: cascade returns failed for everything, vision pick drives a real locator click. (#2) PageStateObserver prompt-diff test proving page_state JSON appears in decomposer's user prompt. (#4) Telemetry harness — TelemetryCounter + TelemetryLLMClient + TelemetryVisualInspector wrappers + runner wiring; per-run metrics in OrchestrationResult.metadata.telemetry (llm_calls, tokens, vision_calls, total_seconds, heal_strategy_counts, step_durations_ms). (#5) ACTION_EXTRACT_RECORD action for single-record PDPs — LLM absolute-CSS selector resolution + double-pass quality guard (rejects "for you"-style garbage) + pattern-first heuristic for typed fields (price/rating) + h1/<title> fallback. Final live Flipkart drill: 3/3 success with REAL fields {title, price, variant}: OnePlus 12 ₹49,869, Mi 14 CIVI ₹44,999, Pixel 10a ₹49,999. Measured cost: 8 LLM calls + ~33k tokens for full phase1+drill×3 workflow. +13 unit tests (292 pass). 7 real-run iterations on Flipkart proving the loop-fix-rerun methodology with measurable evidence each time |

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
