# Symbol Index
> Code symbol registry. AI: look here before searching source files. Add entries as you discover symbols.

---

## Metadata

```
Last Updated      : 2026-05-24
Total Symbols     : 74
Coverage          : PARTIAL (grows incrementally)
```

---

## How to Use

1. Before searching a codebase for a function/class/type, check here first
2. If found: read only the specific file:line range, not the whole file
3. If not found: search the source, then add the entry here before finishing

**Read range tip:** When a symbol is at line N, read lines `N-2` to `N+30` (for a function) or `N-2` to `N+5` (for a constant/import). Adjust based on complexity.

---

## Functions

| Name | File | Line | Signature | Description | Last Verified |
|------|------|------|-----------|-------------|---------------|
| *(no entries yet)* | | | | | |

---

## Classes

| Name | File | Line | Inherits | Responsibility | Last Verified |
|------|------|------|----------|----------------|---------------|
| BidirectionalAnchorFieldStrategy | xpath_healer/core/strategies/bidirectional_anchor_field.py | 62 | Strategy | Bidirectional anchor-text resolver for textbox/dropdown; axis_hint soft tie-breaker | 2026-05-23 |
| AxisHintFieldResolverStrategy | xpath_healer/core/strategies/axis_hint_field.py | 15 | Strategy | Legacy directional resolver (kept as fallback) | 2026-05-23 |
| LabelProximityInteractableStrategy | xpath_healer/core/strategies/label_proximity_interactable.py | 22 | Strategy | Bidirectional resolver for button/checkbox/radio | 2026-05-23 |
| Strategy | xpath_healer/core/strategies/base.py | 11 | ABC | Strategy ABC with id/priority/stage + supports/build | 2026-05-23 |
| GraphContainerGrounder | xpath_healer/core/graph_container.py | 86 | (none) | Find narrowest stable container around an anchor; one DOM evaluate per call | 2026-05-23 |
| GroundedContainer | xpath_healer/core/graph_container.py | 70 | dataclass | Result: path + xpath + candidate_count + diagnostics | 2026-05-23 |
| ElementSignature | xpath_healer/core/models.py | 200 | dataclass | Now carries option_set + container_lca_path; legacy payloads hydrate to empty | 2026-05-23 |
| LLMClient | xpath_healer/llm/client.py | 56 | Protocol | Model-agnostic tool-calling chat contract — single method `chat()` | 2026-05-23 |
| OpenAIChatClient | xpath_healer/llm/openai_chat.py | 34 | LLMClient | OpenAI / Azure OpenAI tool-calling chat impl | 2026-05-23 |
| MCPExploratoryHealer | xpath_healer/mcp/explorer.py | 76 | Protocol | Async `explore()` contract — what any MCP-style healer impl must satisfy | 2026-05-23 |
| AgenticMCPExplorer | xpath_healer/mcp/explorer.py | 136 | MCPExploratoryHealer | Default agent-loop impl: LLM + 3 DOM tools via adapter, bounded budgets | 2026-05-23 |
| ExplorationResult | xpath_healer/mcp/explorer.py | 62 | dataclass | Result: locators[] + rounds + tool_calls_made + metadata | 2026-05-23 |
| WorkflowStep | xpath_healer/core/workflow.py | 38 | dataclass | One step of a multi-step workflow (step_id, intent, action, target_label, target_kind, expected_outcome, optional) | 2026-05-23 |
| StepOutcome | xpath_healer/core/workflow.py | 73 | dataclass | Result of a prior step (status, locator_used, note) — used by healer for stateful reasoning | 2026-05-23 |
| WorkflowContext | xpath_healer/core/workflow.py | 116 | dataclass | Snapshot of workflow around the broken step (workflow_id, intent, current_step, prior_steps, next_step_hint) | 2026-05-23 |
| WORKFLOW_SHAPED_VAR_KEYS | xpath_healer/core/workflow.py | 102 | frozenset | Inventory of var keys that strongly imply workflow misuse via recover_locator (anti-misuse guard) | 2026-05-23 |
| StepRun | xpath_healer/core/workflow.py | 191 | dataclass | Phase 4b: one step's outcome in a workflow run; status starts as heal_*, upgrades to step_* via report_step_outcome | 2026-05-23 |
| WorkflowRun | xpath_healer/core/workflow.py | 247 | dataclass | Phase 4b: ordered append-log of StepRun per workflow_id | 2026-05-23 |
| WorkflowRunRepository | xpath_healer/store/workflow_run_repository.py | 41 | Protocol | Phase 4b: record_step + update_step_status + get_run + find_step_history | 2026-05-23 |
| InMemoryWorkflowRunRepository | xpath_healer/store/workflow_run_repository.py | 77 | WorkflowRunRepository | Phase 4b: pure-dict impl with per-workflow asyncio.Lock and retention cap | 2026-05-23 |
| JsonWorkflowRunRepository | xpath_healer/store/workflow_run_repository.py | 144 | WorkflowRunRepository | Phase 4b: one JSON file per workflow under base_dir; atomic writes; path-traversal safe | 2026-05-23 |
| STEP_STATUS_HEAL_SUCCEEDED | xpath_healer/core/workflow.py | 171 | constant | "heal_succeeded" — recorded by recover_workflow_step on Recovered.status==success | 2026-05-23 |
| WorkflowRewriteProposal | xpath_healer/core/workflow.py | 277 | dataclass | Phase 4c: structured proposal returned by AgenticWorkflowRewriter (action / reason / confidence / metadata) | 2026-05-23 |
| REWRITE_ACTION_SKIP | xpath_healer/core/workflow.py | 269 | constant | "skip" — MVP action for the rewrite agent | 2026-05-23 |
| REWRITE_ACTION_ABORT | xpath_healer/core/workflow.py | 270 | constant | "abort" — MVP action for the rewrite agent | 2026-05-23 |
| is_mvp_rewrite_action | xpath_healer/core/workflow.py | 311 | function | Guard against non-MVP actions (insert_before / replace) reserved for future phases | 2026-05-23 |
| WorkflowRewriter | xpath_healer/workflow/rewriter.py | 84 | Protocol | Async `rewrite(adapter, page, inp, existing_meta, cascade_error) -> RewriteResult` | 2026-05-23 |
| AgenticWorkflowRewriter | xpath_healer/workflow/rewriter.py | 178 | WorkflowRewriter | Bounded agent loop; reuses MCP tool primitives; rejects non-MVP commit actions | 2026-05-23 |
| RewriteResult | xpath_healer/workflow/rewriter.py | 73 | dataclass | Proposal (or None) + rounds + tool_calls_made + metadata | 2026-05-23 |
| compute_page_signature_hash | xpath_healer/core/page_signature.py | 26 | function | Phase 5: 16-char sha256 over stable structure of HTML | 2026-05-24 |
| AutoApplyPolicy | xpath_healer/core/workflow.py | 326 | dataclass | Phase 5: outer-agent policy for proposal.auto_applied flag | 2026-05-24 |
| is_supported_rewrite_action | xpath_healer/core/workflow.py | 320 | function | Phase 5: now accepts all four actions (skip/abort/insert_before/replace) | 2026-05-24 |
| action_requires_new_step | xpath_healer/core/workflow.py | 324 | function | Phase 5: True for insert_before / replace | 2026-05-24 |
| REWRITE_ACTION_INSERT_BEFORE | xpath_healer/core/workflow.py | 271 | constant | Phase 5: now a supported action; requires new_step | 2026-05-24 |
| REWRITE_ACTION_REPLACE | xpath_healer/core/workflow.py | 272 | constant | Phase 5: now a supported action; requires new_step | 2026-05-24 |
| PostgresWorkflowRunRepository | xpath_healer/store/workflow_run_pg_repository.py | 56 | WorkflowRunRepository | Phase 5: PG backend with indexed lookup + in-txn retention prune | 2026-05-24 |
| PlaywrightMCPServerExplorer | xpath_healer/mcp/playwright_mcp_explorer.py | 72 | MCPExploratoryHealer | Phase 5: wraps @playwright/mcp via mcp SDK; graceful fallback when unavailable | 2026-05-24 |
| AppiumPythonAdapter | adapters/appium_python/adapter.py | 173 | AutomationAdapter | Phase 5: mobile adapter; evaluate degrades gracefully (no JS); accessibility-id mapping | 2026-05-24 |
| AppiumRuntimeLocator | adapters/appium_python/adapter.py | 53 | RuntimeLocator | Phase 5: mobile runtime locator with mobile-script forwarding | 2026-05-24 |
| AppiumHealerFacade | adapters/appium_python/facade.py | 14 | BaseHealerFacade | Phase 5: pre-wires AppiumPythonAdapter | 2026-05-24 |
| WorkflowGoal | xpath_healer/orchestrator/models.py | 21 | dataclass | Phase 6: NL goal + start_url + values + constraints + cache_key | 2026-05-24 |
| PlannedWorkflow | xpath_healer/orchestrator/models.py | 41 | dataclass | Phase 6: decomposer output; ordered WorkflowSteps + per-step values | 2026-05-24 |
| ExecutionResult | xpath_healer/orchestrator/models.py | 73 | dataclass | Phase 6: executor return; status + action + detail + page_signal | 2026-05-24 |
| VerificationResult | xpath_healer/orchestrator/models.py | 87 | dataclass | Phase 6: verifier return; ok + tier + reason + confidence | 2026-05-24 |
| OrchestrationResult | xpath_healer/orchestrator/models.py | 116 | dataclass | Phase 6: run() return; status + plan + completed_steps + failed_step | 2026-05-24 |
| GoalDecomposer | xpath_healer/orchestrator/decomposer.py | 87 | Protocol | Phase 6: async decompose(goal, adapter, page) -> PlannedWorkflow | 2026-05-24 |
| AgenticGoalDecomposer | xpath_healer/orchestrator/decomposer.py | 100 | GoalDecomposer | Phase 6: LLM decomposer; reads page outline first; max_attempts retry | 2026-05-24 |
| ActionExecutor | xpath_healer/orchestrator/executor.py | 21 | Protocol | Phase 6: async execute(step, locator, page, value, adapter) -> ExecutionResult | 2026-05-24 |
| PlaywrightActionExecutor | xpath_healer/orchestrator/executor.py | 32 | ActionExecutor | Phase 6: fill/click/select/navigate; natural API first then JS fallback | 2026-05-24 |
| OutcomeVerifier | xpath_healer/orchestrator/verifier.py | 41 | Protocol | Phase 6: async verify(step, execution, adapter, page) -> VerificationResult | 2026-05-24 |
| TieredOutcomeVerifier | xpath_healer/orchestrator/verifier.py | 168 | OutcomeVerifier | Phase 6: auto / structural / LLM tiers; LLM optional; cost-bounded | 2026-05-24 |
| AgenticOutcomeVerifier | xpath_healer/orchestrator/verifier.py | 105 | (helper) | Phase 6: LLM tier; reads compact snapshot, returns {ok,reason,confidence} | 2026-05-24 |
| WorkflowOrchestrator | xpath_healer/orchestrator/runner.py | 80 | (none) | Phase 6+7: top-level coordinator; heal-execute-verify-report; rewrite cascade; recorder + policy-gated visual diagnosis | 2026-05-24 |
| WorkflowRecorder | xpath_healer/orchestrator/recorder.py | 86 | (none) | Phase 7: per-step screenshot or Playwright video; off/screenshots/video modes | 2026-05-24 |
| RecordingInfo | xpath_healer/orchestrator/recorder.py | 35 | dataclass | Phase 7: summary of latest recording (run_id, mode, video_path, screenshots, metadata) | 2026-05-24 |
| StepSnapshot | xpath_healer/orchestrator/recorder.py | 19 | dataclass | Phase 7: one screenshot/timestamp tied to a step_id | 2026-05-24 |
| VisualInspector | xpath_healer/orchestrator/visual.py | 96 | VisualInspectorProto | Phase 7: ffmpeg frames + yt-dlp source + Whisper transcript + multimodal LLM; graceful degrade | 2026-05-24 |
| VisualUsagePolicy | xpath_healer/orchestrator/visual.py | 47 | (constants class) | Phase 7: never / on_failure / on_ambiguous / always | 2026-05-24 |
| FrameSample | xpath_healer/orchestrator/visual.py | 67 | dataclass | Phase 7: one extracted frame ready for the vision LLM | 2026-05-24 |
| InspectionResult | xpath_healer/orchestrator/visual.py | 76 | dataclass | Phase 7: vision-LLM verdict (ok/finding/evidence/frame_index/confidence/suggested_action) | 2026-05-24 |
| ACTION_EXTRACT | xpath_healer/orchestrator/models.py | 75 | constant | Action verb: structured-data pull from a list (LLM selector resolution + heuristic fallback) | 2026-05-24 |
| ACTION_PRESS_KEY | xpath_healer/orchestrator/models.py | 76 | constant | Keyboard input action (Enter/Escape/Tab/ArrowDown...) | 2026-05-24 |
| ACTION_WAIT | xpath_healer/orchestrator/models.py | 77 | constant | Wait for timeout / load state / element state | 2026-05-24 |
| ACTION_SCROLL | xpath_healer/orchestrator/models.py | 78 | constant | Scroll into view / page bottom / pixel scroll | 2026-05-24 |
| ACTION_HOVER | xpath_healer/orchestrator/models.py | 79 | constant | Mouse hover (dropdowns / tooltips) | 2026-05-24 |
| ACTION_SCREENSHOT | xpath_healer/orchestrator/models.py | 80 | constant | Capture artifact for debugging/proof | 2026-05-24 |

---

## Methods (non-trivial)

> Only index methods that are non-obvious or frequently referenced. Skip simple getters/setters.

| Class | Method | File | Line | Description | Last Verified |
|-------|--------|------|------|-------------|---------------|
| GraphContainerGrounder | ground | xpath_healer/core/graph_container.py | 99 | Single-roundtrip ancestor walk: locate anchor, score ancestors by candidate count, return narrowest | 2026-05-23 |
| HealingService | _option_fingerprint_candidates | xpath_healer/core/healing_service.py | 836 | Phase 2 stage: container-grounded option-set healing for label-renamed elements | 2026-05-23 |
| HealingService | _score_option_candidates_in_container | xpath_healer/core/healing_service.py | 915 | JS-side scorer: Jaccard on select options, label/value overlap on radio/checkbox groups, weighted match on inputs | 2026-05-23 |
| HealingService | _mcp_explore_candidates | xpath_healer/core/healing_service.py | 836 | Phase 3 stage: runs ctx.mcp_assist and converts ExplorationResult locators into CandidateSpec entries | 2026-05-23 |
| BaseHealerFacade | _build_mcp_assist_from_env | xpath_healer/api/base.py | 333 | Constructs the default AgenticMCPExplorer; both adapter facades inherit | 2026-05-23 |
| AgenticMCPExplorer | explore | xpath_healer/mcp/explorer.py | 160 | Agent loop: max_rounds × max_tool_calls budget; commit-only-turn early exit | 2026-05-23 |
| BaseHealerFacade | recover_workflow_step | xpath_healer/api/base.py | 138 | Phase 4a workflow-aware healer (keyword-only signature, requires WorkflowContext) | 2026-05-23 |
| BaseHealerFacade | _warn_if_workflow_shaped | xpath_healer/api/base.py | 195 | Logs warning when recover_locator gets workflow-shaped vars — anti-misuse guard | 2026-05-23 |
| BaseHealerFacade | report_step_outcome | xpath_healer/api/base.py | 211 | Phase 4b: outer agent upgrades a heal_* record to step_succeeded / step_failed after attempting the UI action | 2026-05-23 |
| BaseHealerFacade | _record_heal_outcome | xpath_healer/api/base.py | 250 | Phase 4b: best-effort persistence of heal outcome (status, locator, healer_stage, page signature hash) | 2026-05-23 |
| BaseHealerFacade | _build_workflow_run_repository_from_config | xpath_healer/api/base.py | 510 | Phase 4b: builds JsonWorkflowRunRepository or InMemoryWorkflowRunRepository per WorkflowHistoryConfig | 2026-05-23 |
| BaseHealerFacade | _build_workflow_rewriter_from_env | xpath_healer/api/base.py | 510 | Phase 4c: builds AgenticWorkflowRewriter when stages.workflow_rewrite=True AND OpenAI key present | 2026-05-23 |
| BaseHealerFacade | _attach_rewrite_proposal | xpath_healer/api/base.py | 250 | Phase 4c: runs rewriter after cascade failure; never mutates Recovered.status | 2026-05-23 |
| HealingService | _workflow_replay_candidates | xpath_healer/core/healing_service.py | 836 | Phase 4c replay cache: queries workflow_run_repository for prior succeeded records, two-tier trust, bounded to top 3 | 2026-05-23 |

---

## Types / Interfaces / Schemas

| Name | File | Line | Kind | Fields (key ones) | Last Verified |
|------|------|------|------|-------------------|---------------|
| *(no entries yet)* | | | | | |

---

## Constants / Enums

| Name | File | Line | Value / Members | Used For | Last Verified |
|------|------|------|-----------------|----------|---------------|
| _INTENT_SUBTYPE_KEYWORDS | xpath_healer/core/strategies/bidirectional_anchor_field.py | 41 | label-keyword → input @type tuples (email/password/tel/date/number/url/search) | Deterministic intent-subtype inference from label text | 2026-05-23 |
| _PRECEDING_HINTS | xpath_healer/core/strategies/bidirectional_anchor_field.py | 51 | {"preceding","left","above","before","up","previous"} | Normalize axis_hint into preceding-direction boolean | 2026-05-23 |

---

## Public API Surface

> Functions/methods that are explicitly exported or called by external code.

| Symbol | File | Line | Exported As | Callers (known) |
|--------|------|------|-------------|-----------------|
| *(no entries yet)* | | | | |

---

## Symbol Aliases & Renames

> Track symbols that were renamed to avoid confusion.

| Old Name | New Name | File | Changed On | Reason |
|----------|----------|------|------------|--------|
| *(none)* | | | | |

---

## Template: Adding a Symbol Entry

**Function:**
```
| heal_locator | src/healer/core.py | 142 | (locator: str, context: PageContext) -> HealResult | Main healing entrypoint | 2026-04-07 |
```

**Class:**
```
| HealerOrchestrator | src/healer/orchestrator.py | 18 | BaseOrchestrator | Coordinates LLM + DB healing pipeline | 2026-04-07 |
```

**Rules:**
- File paths are relative to project root
- Line number = the `def`, `class`, `const`, or `type` declaration line
- Keep descriptions to one line
- `Last Verified` = last time you confirmed this symbol still exists at this location
- If a symbol moves, update the line number and set Last Verified to today
- If a symbol is deleted, remove the row (or mark `DELETED`)
