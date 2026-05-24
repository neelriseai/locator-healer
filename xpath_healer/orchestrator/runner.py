"""WorkflowOrchestrator — the deterministic glue.

Top-level coordinator. Reuses the existing locator-healer cascade
(``BaseHealerFacade.recover_workflow_step``), the rewrite agent's
``WorkflowRewriteProposal`` plumbing, and the workflow run repository
for replay. Only :class:`AgenticGoalDecomposer` and the LLM-tier of
:class:`TieredOutcomeVerifier` consume tokens.

Flow per ``run()`` call:

  1. Optional navigate to ``goal.start_url`` (if no current page).
  2. ``decomposer.decompose(goal, adapter, page)`` → ``PlannedWorkflow``.
  3. For each step (in order):
     a. ``facade.recover_workflow_step(...)`` — locator (deterministic
        cascade → agent → RAG).
     b. ``executor.execute(step, locator, page, value)`` — drive the
        page deterministically.
     c. ``verifier.verify(step, execution, adapter, page)`` — tiered.
     d. ``facade.report_step_outcome(succeeded=...)`` — feed the
        replay cache.
     e. If failed AND ``rewrite_proposal``: honour skip / abort /
        insert_before (re-execute new step) / replace (substitute the
        rest of this step's locator-finding).
  4. Return :class:`OrchestrationResult`.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import LocatorSpec, Recovered
from xpath_healer.core.workflow import (
    REWRITE_ACTION_ABORT,
    REWRITE_ACTION_INSERT_BEFORE,
    REWRITE_ACTION_REPLACE,
    REWRITE_ACTION_SKIP,
    StepOutcome,
    WorkflowContext,
    WorkflowStep,
)
from xpath_healer.orchestrator.decomposer import GoalDecomposer
from xpath_healer.orchestrator.executor import ActionExecutor
from xpath_healer.orchestrator.models import (
    ACTION_CLICK,
    ACTION_EXTRACT,
    ACTION_FILL,
    ACTION_HOVER,
    ACTION_NAVIGATE,
    ACTION_PRESS_KEY,
    ACTION_SCREENSHOT,
    ACTION_SCROLL,
    ACTION_SELECT,
    ACTION_VERIFY,
    ACTION_WAIT,
    ExecutionResult,
    OrchestrationResult,
    PlannedWorkflow,
    StepRunRecord,
    VerificationResult,
    WorkflowGoal,
)


# Browser-side JS used by the candidate-based visual heal. Extracts
# the top ~40 clickable / interactable elements with their text, role,
# aria-label, bounding box, and a best-effort stable CSS selector.
# Stays well below 8 KB so we can ship it through Playwright's evaluate.
_CANDIDATE_EXTRACTION_JS = r"""
() => {
    const MAX = 40;
    const sels = [
        'button',
        'a[href]',
        'input',
        'select',
        'textarea',
        '[role="button"]',
        '[role="link"]',
        '[role="checkbox"]',
        '[role="radio"]',
        '[role="menuitem"]',
        '[role="option"]',
        '[role="tab"]',
        '[role="combobox"]',
        '[role="textbox"]',
        '[onclick]',
    ];
    const seen = new Set();
    const out = [];
    function visibleEnough(el, r) {
        if (r.width < 6 || r.height < 6) return false;
        const style = window.getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none') return false;
        if (parseFloat(style.opacity) === 0) return false;
        return true;
    }
    function bestSelector(el) {
        if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) return '#' + el.id;
        const data = ['data-testid', 'data-test', 'data-qa', 'data-cy'];
        for (const a of data) {
            const v = el.getAttribute(a);
            if (v) return `[${a}="${CSS.escape(v)}"]`;
        }
        const tag = el.tagName.toLowerCase();
        const aria = el.getAttribute('aria-label');
        if (aria) return `${tag}[aria-label="${CSS.escape(aria)}"]`;
        const name = el.getAttribute('name');
        if (name) return `${tag}[name="${CSS.escape(name)}"]`;
        // Fall back to a class chain that picks no more than 3 stable looking classes.
        const classes = Array.from(el.classList || []).filter(
            c => c && !/^(?:active|hover|focus|selected)/i.test(c) && c.length <= 32
        ).slice(0, 3);
        if (classes.length) return tag + '.' + classes.map(c => CSS.escape(c)).join('.');
        return tag;
    }
    for (const sel of sels) {
        let els;
        try { els = document.querySelectorAll(sel); } catch (_) { continue; }
        for (const el of els) {
            if (seen.has(el)) continue;
            const r = el.getBoundingClientRect();
            if (!visibleEnough(el, r)) continue;
            // Skip elements outside the viewport — vision can only see what's painted.
            if (r.bottom < 0 || r.top > window.innerHeight) continue;
            seen.add(el);
            const text = (el.innerText || el.value || '').trim().slice(0, 120);
            out.push({
                index: out.length,
                tag: el.tagName.toLowerCase(),
                text: text,
                role: el.getAttribute('role') || '',
                aria_label: el.getAttribute('aria-label') || '',
                placeholder: el.getAttribute('placeholder') || '',
                href: el.getAttribute('href') || '',
                type: el.getAttribute('type') || '',
                css_selector: bestSelector(el),
                bbox: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
                visible: true,
                enabled: !el.disabled,
            });
            if (out.length >= MAX) return out;
        }
    }
    return out;
}
"""


# Action → field_type mapping. The healer's validator branches on
# field_type; picking the right one prevents false rejections like
# "text_mismatch" on inputs whose inner text is empty.
_ACTION_FIELD_TYPE: dict[str, str] = {
    ACTION_FILL: "textbox",
    ACTION_PRESS_KEY: "textbox",
    ACTION_SELECT: "dropdown",
    ACTION_CLICK: "button",
    ACTION_HOVER: "button",
    ACTION_SCROLL: "generic",
    ACTION_EXTRACT: "generic",
    ACTION_NAVIGATE: "generic",
    ACTION_VERIFY: "generic",
    ACTION_SCREENSHOT: "generic",
}


def _derive_field_type(step: WorkflowStep) -> str:
    """If the decomposer supplied a target_kind, honour it; else map
    from the action verb."""
    explicit = (step.target_kind or "").strip().lower()
    if explicit:
        return explicit
    return _ACTION_FIELD_TYPE.get((step.action or "").strip().lower(), "generic")
from xpath_healer.orchestrator.verifier import OutcomeVerifier


class WorkflowOrchestrator:
    """End-to-end goal runner. Deterministic glue around healer + agents.

    Optional vision feature (Phase 7):
      * ``recorder``         — captures screenshots / video of the run
      * ``visual_inspector`` — vision-LLM diagnosis of failures
      * ``visual_policy``    — never / on_failure / on_ambiguous / always
    """

    def __init__(
        self,
        *,
        facade: Any,
        decomposer: GoalDecomposer,
        executor: ActionExecutor,
        verifier: OutcomeVerifier,
        auto_apply_policy: Any | None = None,
        max_recovery_inserts: int = 3,
        recorder: Any | None = None,
        visual_inspector: Any | None = None,
        visual_policy: str = "on_failure",
        visual_ambiguous_confidence_threshold: float = 0.6,
        visual_override_threshold: float = 0.8,
        visual_block_override_threshold: float = 0.95,
        visual_recovery_enabled: bool = True,
        replan_on_url_change: bool = True,
        max_replans: int = 2,
    ) -> None:
        self.facade = facade
        self.decomposer = decomposer
        self.executor = executor
        self.verifier = verifier
        self.auto_apply_policy = auto_apply_policy
        self.max_recovery_inserts = max(0, int(max_recovery_inserts))
        self.recorder = recorder
        self.visual_inspector = visual_inspector
        # Lazy import to avoid forcing visual.py imports at runner load.
        from xpath_healer.orchestrator.visual import VisualUsagePolicy

        self.visual_policy = VisualUsagePolicy.normalize(visual_policy)
        self.visual_ambig_threshold = float(visual_ambiguous_confidence_threshold)
        # Vision must be at least this confident to override a text-tier
        # verdict. Default 0.8 — tuned so casual "looks ok" doesn't
        # reverse a hard failure.
        self.visual_override_threshold = float(visual_override_threshold)
        # If the text-tier verifier was MORE confident than this,
        # vision is overruled (text-tier had strong evidence). Defaults
        # to 0.95: because the LLM verifier reads compressed DOM text
        # rather than pixels, it caps itself at 0.85 internally — so
        # anything above 0.95 has to come from a structural or auto-tier
        # verdict, which deserves the deference.
        self.visual_block_override_threshold = float(visual_block_override_threshold)
        self.visual_recovery_enabled = bool(visual_recovery_enabled)
        # Replan: when a navigation-class step succeeds (search submission,
        # link click that changed the URL), re-decompose the rest of the
        # goal on the new page so we don't run plans rooted in a stale
        # outline. Capped to ``max_replans`` per workflow.
        self.replan_on_url_change = bool(replan_on_url_change)
        self.max_replans = max(0, int(max_replans))
        self.logger = logging.getLogger("xpath_healer.orchestrator.runner")

    async def run(
        self,
        *,
        page: Any,
        goal: WorkflowGoal,
        adapter: AutomationAdapter | None = None,
    ) -> OrchestrationResult:
        adapter = adapter or self.facade.adapter

        # Optional recording for visual diagnosis.
        run_id = goal.cache_key()
        if self.recorder is not None:
            try:
                self.recorder.start(run_id=run_id)
            except Exception:
                self.logger.exception("recorder.start failed (non-fatal)")

        # Step 0 — open the start URL if one was provided.
        if goal.start_url:
            nav = await self.executor.execute(
                step=WorkflowStep(
                    step_id="open_start_url",
                    intent="navigate to start url",
                    action=ACTION_NAVIGATE,
                    target_label=goal.start_url,
                ),
                locator=None,
                page=page,
                value=goal.start_url,
                adapter=adapter,
            )
            if nav.status != "ok":
                return OrchestrationResult(
                    status="failed",
                    goal=goal,
                    plan=None,
                    metadata={"error": f"navigate failed: {nav.detail}"},
                )

        # Step 1 — decompose.
        plan = await self.decomposer.decompose(goal=goal, adapter=adapter, page=page)
        if not plan.steps:
            return OrchestrationResult(
                status="failed",
                goal=goal,
                plan=plan,
                metadata={"error": "decomposer_produced_no_steps", "decomposer": plan.metadata},
            )

        completed: list[StepRunRecord] = []
        prior_outcomes: list[StepOutcome] = []
        inserts_remaining = self.max_recovery_inserts
        replans_remaining = self.max_replans
        last_plan_url = await self._current_url(page)
        # Cap vision-derived inserts per step_id so an unfixable element
        # doesn't trigger an endless "vision proposes dismiss → that
        # succeeds → original still fails → vision proposes again" loop.
        vision_inserts_per_step: dict[str, int] = {}
        i = 0
        while i < len(plan.steps):
            current = plan.steps[i]
            next_hint = plan.steps[i + 1] if (i + 1) < len(plan.steps) else None
            value = plan.value_for(current.step_id)
            wf_ctx = WorkflowContext(
                workflow_id=plan.workflow_id,
                workflow_intent=goal.text,
                current_step=current,
                prior_steps=list(prior_outcomes[-5:]),
                next_step_hint=next_hint,
                metadata={"goal_cache_key": goal.cache_key()},
            )

            record, terminal, new_step = await self._run_step(
                page=page,
                adapter=adapter,
                step=current,
                value=value,
                workflow_context=wf_ctx,
                vision_inserts_per_step=vision_inserts_per_step,
            )
            completed.append(record)

            # Post-step snapshot for the recorder (no-op when recorder
            # is None / mode is off).
            if self.recorder is not None:
                try:
                    await self.recorder.snapshot(
                        step_id=current.step_id,
                        action=current.action,
                        page=page,
                        note="post-step",
                    )
                except Exception:
                    self.logger.exception("post-step snapshot failed (non-fatal)")

            # Decide whether to invoke the visual inspector.
            await self._maybe_visual_diagnosis(record=record, terminal=terminal)

            # Gap #1 — vision can promote a text-tier false-negative to
            # ok when it is high-confidence and the text tier was not.
            terminal = self._revise_terminal_with_vision(record=record, terminal=terminal)

            # Gap #3 — when vision spotted a blocking modal / captcha and
            # we still have rewrite budget, synthesise a rewrite proposal
            # so the loop self-heals instead of just failing. Per-step
            # cap of 1 vision-derived insert prevents pathological
            # cascades when the original step is fundamentally unfixable.
            if terminal in {"fail", "abort"}:
                if vision_inserts_per_step.get(current.step_id, 0) < 1:
                    proposal = self._proposal_from_vision(record=record, step=current)
                    if proposal is not None:
                        v_terminal, v_applied, v_new_step = self._handle_rewrite(
                            step=current, proposal=proposal
                        )
                        if v_terminal != "fail":
                            record.rewrite_applied = (
                                (record.rewrite_applied + "+" if record.rewrite_applied else "")
                                + f"vision:{v_applied}"
                            )
                            terminal = v_terminal
                            new_step = v_new_step
                            vision_inserts_per_step[current.step_id] = (
                                vision_inserts_per_step.get(current.step_id, 0) + 1
                            )

            if record.execution and record.execution.status == "skipped":
                prior_outcomes.append(
                    StepOutcome(
                        step_id=current.step_id,
                        status="skipped",
                        note=record.rewrite_applied or "step optional",
                    )
                )
                i += 1
                continue

            if terminal == "abort":
                return OrchestrationResult(
                    status="aborted",
                    goal=goal,
                    plan=plan,
                    completed_steps=completed,
                    failed_step=record,
                    metadata={
                        "abort_reason": (
                            (record.execution.detail if record.execution else "")
                            or (record.verification.reason if record.verification else "")
                        ),
                    },
                )

            if terminal == "fail":
                return OrchestrationResult(
                    status="failed",
                    goal=goal,
                    plan=plan,
                    completed_steps=completed,
                    failed_step=record,
                )

            if terminal == "insert_before":
                # Insert the new step at position i so it becomes the
                # next thing executed. Current step retries afterwards.
                if inserts_remaining <= 0 or new_step is None:
                    return OrchestrationResult(
                        status="failed",
                        goal=goal,
                        plan=plan,
                        completed_steps=completed,
                        failed_step=record,
                        metadata={
                            "error": (
                                "insert_budget_exhausted"
                                if inserts_remaining <= 0
                                else "rewrite_insert_missing_new_step"
                            )
                        },
                    )
                inserts_remaining -= 1
                plan.steps.insert(i, new_step)
                # Loop: don't increment i — the inserted step is now at i.
                continue

            if terminal == "replace":
                # Replace current step with new_step; don't advance i so
                # the new step runs next (and the original is dropped).
                if inserts_remaining <= 0 or new_step is None:
                    return OrchestrationResult(
                        status="failed",
                        goal=goal,
                        plan=plan,
                        completed_steps=completed,
                        failed_step=record,
                        metadata={
                            "error": (
                                "insert_budget_exhausted"
                                if inserts_remaining <= 0
                                else "rewrite_replace_missing_new_step"
                            )
                        },
                    )
                inserts_remaining -= 1
                plan.steps[i] = new_step
                continue

            # terminal == "ok"
            outcome_status = "success" if (record.verification and record.verification.ok) else "step_succeeded"
            prior_outcomes.append(
                StepOutcome(
                    step_id=current.step_id,
                    status=outcome_status,
                    locator_used=record.locator_value or "",
                )
            )
            i += 1

            # Replan if this step likely caused a major page change AND
            # there is more plan left. We only consult the URL because
            # it is cheap; if it differs from the URL the decomposer
            # planned for, the remaining steps probably target the
            # wrong page.
            if self.replan_on_url_change and i < len(plan.steps) and replans_remaining > 0:
                if await self._page_changed_significantly(
                    page=page, since_url=last_plan_url
                ):
                    self.logger.info(
                        "replan triggered after %s (i=%d) — re-decomposing remaining goal",
                        current.step_id, i,
                    )
                    remaining_steps = await self._replan_remaining(
                        goal=goal,
                        adapter=adapter,
                        page=page,
                        completed_step_ids=[r.step_id for r in completed],
                    )
                    if remaining_steps:
                        # Drop the stale tail; splice in the fresh plan.
                        del plan.steps[i:]
                        plan.steps.extend(remaining_steps.steps)
                        # Merge the new step values into the plan's
                        # value map so executor still sees its inputs.
                        for k, v in remaining_steps.values_by_step.items():
                            plan.values_by_step[k] = v
                        last_plan_url = await self._current_url(page)
                        replans_remaining -= 1
                    else:
                        # Replan returned nothing — keep going with the
                        # original plan. The healer will likely fail; we
                        # don't loop replanning forever.
                        replans_remaining -= 1

        # Aggregate extract-action outputs.
        extracted: dict[str, list[dict[str, Any]]] = {}
        for rec in completed:
            exe = rec.execution
            if exe is None or exe.status != "ok":
                continue
            payload = (exe.page_signal or {}).get("extracted")
            if isinstance(payload, list):
                extracted[rec.step_id] = [
                    dict(item) if isinstance(item, dict) else {"value": str(item)}
                    for item in payload
                ]
        return OrchestrationResult(
            status="success",
            goal=goal,
            plan=plan,
            completed_steps=completed,
            extracted_data=extracted,
            metadata={
                "step_count": len(completed),
                "verifier_tiers": {
                    rec.step_id: (rec.verification.tier if rec.verification else "n/a")
                    for rec in completed
                },
            },
        )

    # ------------------------------------------------------------------
    # Per-step driver
    # ------------------------------------------------------------------

    async def _run_step(
        self,
        *,
        page: Any,
        adapter: AutomationAdapter,
        step: WorkflowStep,
        value: str,
        workflow_context: WorkflowContext,
        vision_inserts_per_step: dict[str, int] | None = None,
    ) -> tuple[StepRunRecord, str, WorkflowStep | None]:
        """Execute one step. Returns ``(record, terminal, new_step)``.

        ``terminal`` is one of:
          * ``"ok"``            — step completed, advance
          * ``"fail"``          — terminal failure, abort run as failed
          * ``"abort"``         — rewriter said abort, stop run as aborted
          * ``"insert_before"`` — insert ``new_step`` before current, retry
          * ``"replace"``       — replace current with ``new_step``, retry

        ``new_step`` is None unless terminal in {insert_before, replace}.
        """
        record = StepRunRecord(
            step_id=step.step_id,
            action=step.action,
            target_label=step.target_label,
        )
        start_ns = time.perf_counter_ns()

        # Verify-only, navigate, timer-wait, and screenshot steps don't
        # need a locator; skip straight to execution / verification.
        locator_less = step.action in (ACTION_NAVIGATE, ACTION_VERIFY, ACTION_SCREENSHOT)
        if step.action == ACTION_WAIT and not step.target_label:
            # wait with no target = timer / page load state
            locator_less = True
        if locator_less:
            execution = await self.executor.execute(
                step=step,
                locator=None,
                page=page,
                value=value,
                adapter=adapter,
            )
            record.execution = execution
            verification = await self.verifier.verify(
                step=step, execution=execution, adapter=adapter, page=page
            )
            record.verification = verification
            record.duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            if execution.status == "error" and not step.optional:
                return record, "fail", None
            return record, "ok", None

        # All other actions need a locator first.
        fallback = LocatorSpec(
            kind="xpath",
            value=f"//xh-never-match[@step='{step.step_id}']",
        )
        vars_map = self._vars_for(step, value)
        field_type = _derive_field_type(step)
        recovered: Recovered = await self.facade.recover_workflow_step(
            page=page,
            app_id=workflow_context.workflow_id or "orchestrator",
            page_name=step.target_kind or "step",
            element_name=step.step_id,
            field_type=field_type,
            fallback=fallback,
            vars=vars_map,
            workflow_context=workflow_context,
            auto_apply_policy=self.auto_apply_policy,
        )
        record.heal_status = recovered.status
        record.heal_strategy = recovered.strategy_id or ""
        if recovered.locator_spec is not None:
            record.locator_kind = recovered.locator_spec.kind
            record.locator_value = recovered.locator_spec.value

        if recovered.status != "success":
            # Optional steps short-circuit on heal-fail UNLESS the
            # rewriter already produced a proposal worth honouring.
            # A dismiss-popup step that finds no popup is the WINNING
            # outcome ("nothing to dismiss, page is clean"); spending
            # vision-recovery cost only invites the "vision sees adjacent
            # modal, proposes dismiss, cycle repeats" loop.
            if step.optional and recovered.rewrite_proposal is None:
                record.rewrite_applied = "optional_heal_miss_skip"
                record.execution = ExecutionResult(
                    status="skipped",
                    action=step.action,
                    detail="optional step: heal cascade found no target",
                )
                record.duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                return record, "ok", None

            # Candidate-based visual heal (per "Locator healer eyes" doc).
            # Before falling back to modal-detection vision, try the
            # candidate-based vision pick: extract DOM candidates +
            # screenshot, ask the model which one matches the intent,
            # build a fresh locator from the chosen candidate's css
            # selector. Only fires for click / fill / hover / press_key
            # / select / scroll — actions that target a specific element.
            visual_candidate_actions = {
                ACTION_CLICK, ACTION_FILL, ACTION_HOVER, ACTION_PRESS_KEY,
                ACTION_SELECT, ACTION_SCROLL,
            }
            already_used = (
                (vision_inserts_per_step or {}).get(step.step_id, 0)
                if vision_inserts_per_step is not None
                else 0
            )
            if (
                step.action in visual_candidate_actions
                and self.visual_inspector is not None
                and already_used < 1
            ):
                cand_locator = await self._try_visual_candidate_heal(
                    page=page, step=step
                )
                if cand_locator is not None:
                    # Execute through the candidate-derived locator.
                    record.heal_strategy = "visual_candidate_pick"
                    exec_result = await self.executor.execute(
                        step=step,
                        locator=cand_locator,
                        page=page,
                        value=value,
                        adapter=adapter,
                    )
                    record.execution = exec_result
                    verification = await self.verifier.verify(
                        step=step, execution=exec_result, adapter=adapter, page=page
                    )
                    record.verification = verification
                    record.duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                    if vision_inserts_per_step is not None:
                        vision_inserts_per_step[step.step_id] = already_used + 1
                    if exec_result.status == "ok" and (verification.ok or step.optional):
                        return record, "ok", None
                    if exec_result.status == "error" and not step.optional:
                        return record, "fail", None
                    if not verification.ok and not step.optional:
                        return record, "fail", None
                    return record, "ok", None

            # extract is a special case: its target ("product cards",
            # "result list") is a structural pattern, not a text label.
            # If the heal cascade can't find it, try the executor's
            # JS-only repeating-structure auto-discovery FIRST before
            # falling back to rewrite / vision. This is cheap and
            # usually nails Amazon/Flipkart/Google-shaped result lists.
            if step.action == ACTION_EXTRACT:
                self.logger.info(
                    "extract heal failed; trying repeating-structure auto-discovery"
                )
                exec_result = await self.executor.execute(
                    step=step,
                    locator=None,
                    page=page,
                    value=value,
                    adapter=adapter,
                )
                record.execution = exec_result
                verification = await self.verifier.verify(
                    step=step, execution=exec_result, adapter=adapter, page=page
                )
                record.verification = verification
                record.heal_strategy = "extract_auto_discover"
                record.duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                if exec_result.status == "ok" and (
                    verification.ok or step.optional
                ):
                    return record, "ok", None
                # Auto-discover didn't pan out — fall through to the
                # rewrite / vision path with the heal cascade's findings.

            # Healer failed. Consult the rewrite proposal (if any). If
            # the rewriter had no idea, give vision a chance — it can
            # spot blocking modals / captchas the DOM-mining heuristics
            # miss. Whichever proposal is stronger wins (highest
            # confidence; vision tie-breaks on equal confidence).
            proposal = recovered.rewrite_proposal
            vision_proposal: Any | None = None
            # Per-step vision recovery cap: 1 try per step_id across
            # both gap #2 (heal-failed) and gap #3 (post-terminal) paths.
            # Prevents pathological "vision proposes dismiss, succeeds,
            # original still fails, vision proposes again" cascades.
            already_used = (
                (vision_inserts_per_step or {}).get(step.step_id, 0)
                if vision_inserts_per_step is not None
                else 0
            )
            if (proposal is None or float(getattr(proposal, "confidence", 0.0) or 0.0) < 0.6) and already_used < 1:
                vision_proposal, vision_finding = await self._try_visual_recovery(
                    page=page, step=step
                )
                if vision_finding is not None:
                    # Stash on the record so the post-step diagnosis path
                    # can see we already inspected and skip the 2nd call.
                    record.visual_finding = vision_finding
            chosen = self._pick_stronger_proposal(proposal, vision_proposal)

            terminal, applied, new_step = self._handle_rewrite(
                step=step, proposal=chosen
            )
            record.rewrite_applied = applied
            if vision_proposal is not None and chosen is vision_proposal:
                record.rewrite_applied = (
                    (record.rewrite_applied + "+" if record.rewrite_applied else "")
                    + "from_vision"
                )
                if vision_inserts_per_step is not None:
                    vision_inserts_per_step[step.step_id] = already_used + 1
            record.duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            if terminal == "skip":
                record.execution = ExecutionResult(
                    status="skipped", action=step.action, detail=f"rewrite:skip ({applied})"
                )
                return record, "ok", None  # caller treats skipped uniformly
            return record, terminal, new_step

        # Locator found — execute.
        runtime_locator = recovered.playwright_locator or recovered.runtime_locator
        execution = await self.executor.execute(
            step=step,
            locator=runtime_locator,
            page=page,
            value=value,
            adapter=adapter,
        )
        record.execution = execution

        # Verify.
        verification = await self.verifier.verify(
            step=step, execution=execution, adapter=adapter, page=page
        )
        record.verification = verification

        # Close the loop on the workflow run repo so the cache can
        # promote heal_succeeded → step_succeeded.
        try:
            succeeded = execution.status == "ok" and verification.ok
            await self.facade.report_step_outcome(
                workflow_id=workflow_context.workflow_id,
                step_id=step.step_id,
                succeeded=succeeded,
                note=f"orch:{step.action}:{verification.tier}",
            )
        except Exception:
            self.logger.exception("report_step_outcome failed (non-fatal)")

        record.duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        if execution.status == "error" and not step.optional:
            return record, "fail", None
        if not verification.ok and not step.optional:
            return record, "fail", None
        return record, "ok", None

    # ------------------------------------------------------------------
    # Replan helpers (re-decompose when the page changes drastically)
    # ------------------------------------------------------------------

    @staticmethod
    async def _current_url(page: Any) -> str:
        """Get the current page URL safely. Returns '' on failure."""
        try:
            url_attr = getattr(page, "url", "")
            if isinstance(url_attr, str):
                return url_attr
            # Some adapters expose url as a coroutine/callable.
            if callable(url_attr):
                val = url_attr()
                if hasattr(val, "__await__"):
                    val = await val
                return str(val or "")
        except Exception:
            return ""
        return ""

    @classmethod
    async def _page_changed_significantly(
        cls,
        *,
        page: Any,
        since_url: str,
    ) -> bool:
        """Heuristic: a URL change to a different path-segment counts as
        a significant page change. Same path (only query / fragment
        changed) does not — many SPAs reflect filter state in the URL
        without re-rendering the whole shell.
        """
        now = await cls._current_url(page)
        if not now:
            return False
        if not since_url:
            return True
        # Compare path roots quickly.
        try:
            from urllib.parse import urlparse

            a, b = urlparse(since_url), urlparse(now)
        except Exception:
            return now != since_url
        if a.netloc != b.netloc:
            return True
        # Coalesce trailing slashes.
        pa = (a.path or "/").rstrip("/")
        pb = (b.path or "/").rstrip("/")
        return pa != pb

    async def _replan_remaining(
        self,
        *,
        goal: WorkflowGoal,
        adapter: AutomationAdapter,
        page: Any,
        completed_step_ids: list[str],
    ) -> PlannedWorkflow | None:
        """Re-decompose the goal on the CURRENT page. Returns the new
        sub-plan covering the remaining work. The decomposer sees the
        full goal but with a 'so_far' constraint listing the step_ids
        we've already completed so it doesn't re-emit them."""
        replan_goal = WorkflowGoal(
            text=goal.text,
            start_url="",  # we are already on the right page
            values=dict(goal.values),
            constraints={
                **dict(goal.constraints),
                "completed_step_ids": completed_step_ids,
                "replanning": True,
            },
        )
        try:
            sub_plan = await self.decomposer.decompose(
                goal=replan_goal, adapter=adapter, page=page
            )
        except Exception:
            self.logger.exception("replan decompose failed")
            return None
        if not sub_plan.steps:
            return None
        # Drop any steps the decomposer re-emitted by step_id — defensive.
        seen = set(completed_step_ids)
        sub_plan.steps = [s for s in sub_plan.steps if s.step_id not in seen]
        # Steps it didn't bother to rename may also collide with
        # remaining tail step_ids. Suffix duplicates so the orchestrator
        # never trips on duplicate ids.
        seen_now: set[str] = set()
        for s in sub_plan.steps:
            base = s.step_id
            suffix = 0
            while s.step_id in seen_now:
                suffix += 1
                s.step_id = f"{base}__rp{suffix}"
            seen_now.add(s.step_id)
        return sub_plan if sub_plan.steps else None

    # ------------------------------------------------------------------
    # Visual diagnosis (Phase 7)
    # ------------------------------------------------------------------

    async def _maybe_visual_diagnosis(
        self,
        *,
        record: StepRunRecord,
        terminal: str,
    ) -> None:
        """Run the vision inspector if the policy says so. Attaches the
        result to ``record.visual_finding``. Best-effort — failures are
        swallowed so they never break the orchestrator loop."""
        if self.visual_inspector is None or self.recorder is None:
            return
        # If the heal-failed visual-recovery path already inspected, do
        # NOT spend a second vision call.
        if record.visual_finding is not None:
            return
        from xpath_healer.orchestrator.visual import VisualUsagePolicy

        policy = self.visual_policy
        if policy == VisualUsagePolicy.NEVER:
            return

        # Decide whether to spend a vision call based on the policy.
        should_inspect = False
        reason = ""
        if policy == VisualUsagePolicy.ALWAYS:
            should_inspect = True
            reason = "policy=always"
        elif terminal in {"fail", "abort"}:
            should_inspect = policy in {
                VisualUsagePolicy.ON_FAILURE,
                VisualUsagePolicy.ON_AMBIGUOUS,
                VisualUsagePolicy.ALWAYS,
            }
            reason = "step_failed"
        elif policy == VisualUsagePolicy.ON_AMBIGUOUS:
            v = record.verification
            if v is not None and v.confidence < self.visual_ambig_threshold:
                should_inspect = True
                reason = f"verifier_confidence_{v.confidence:.2f}_below_{self.visual_ambig_threshold:.2f}"
        if not should_inspect:
            return

        # Build the question + collect frame paths around this step.
        info = getattr(self.recorder, "last_recording", None)
        if info is None:
            return
        related_paths: list[str] = []
        try:
            for snap in getattr(info, "screenshots", [])[-6:]:
                p = getattr(snap, "screenshot_path", "")
                if p:
                    related_paths.append(p)
        except Exception:
            pass

        question = self._diagnosis_question(record=record, reason=reason)
        try:
            finding = await self.visual_inspector.inspect(
                question=question,
                video_path=getattr(info, "video_path", "") or "",
                screenshots=related_paths,
                max_frames=6,
            )
        except Exception:
            self.logger.exception("visual inspector raised (non-fatal)")
            return
        record.visual_finding = finding

    @staticmethod
    def _diagnosis_question(record: StepRunRecord, reason: str) -> str:
        action = record.action or "step"
        label = record.target_label or "(no label)"
        exec_part = ""
        if record.execution is not None:
            exec_part = (
                f"\nExecutor said: status={record.execution.status} "
                f"detail={record.execution.detail!r}"
            )
        verify_part = ""
        if record.verification is not None:
            verify_part = (
                f"\nText-tier verifier ({record.verification.tier}) said: "
                f"ok={record.verification.ok} reason={record.verification.reason!r} "
                f"confidence={record.verification.confidence}"
            )
        # Phase A.4 — Targeted question. We ask the model to compare the
        # FIRST and LAST frame so it can pinpoint state changes
        # ("pattern interrupts" per the video-reading spec).
        return (
            f"The orchestrator just ran step '{record.step_id}' "
            f"(action={action}, target={label!r}). Trigger={reason}."
            f"{exec_part}{verify_part}\n\n"
            "TASK: Compare the FIRST frame (before this step) to the LAST "
            "frame (after this step) and decide if the intended outcome "
            "actually happened.\n"
            "Be specific: did the URL/title change? Did a results list or "
            "next-page widget appear? Did a modal block the view? Is there "
            "a captcha / Cloudflare wall / 'access denied' / 'sign in' "
            "wall? If a modal is blocking, name its visible close button "
            "(e.g. 'X', 'Skip', 'Maybe later') in suggested_action.\n"
            "Return JSON: {finding, evidence, frame_index, confidence (0-1, "
            "high only when sure), suggested_action}. Use the special "
            "suggested_action prefixes when applicable:\n"
            "  - 'dismiss_modal:<close button label>' if a modal blocks us\n"
            "  - 'abort:captcha' / 'abort:login_wall' if site refuses bots\n"
            "  - 'retry' if the step looks like a transient miss\n"
            "  - '' if no action is needed."
        )

    # ------------------------------------------------------------------
    # Gap #1 — Vision overrides a text-tier verdict.
    # ------------------------------------------------------------------

    def _revise_terminal_with_vision(
        self,
        *,
        record: StepRunRecord,
        terminal: str,
    ) -> str:
        """Promote a text-tier ``fail`` to ``ok`` when vision is
        high-confidence the step actually succeeded AND the text-tier
        verifier was not confident in its negative verdict.

        Returns a possibly-revised terminal. Mutates ``record.verification``
        to leave an audit trail when an override fires.
        """
        if terminal != "fail":
            return terminal
        vf = record.visual_finding
        if vf is None:
            return terminal
        if not bool(getattr(vf, "ok", False)):
            return terminal
        vision_conf = float(getattr(vf, "confidence", 0.0) or 0.0)
        if vision_conf < self.visual_override_threshold:
            return terminal
        verify_conf = (
            float(record.verification.confidence)
            if (record.verification and record.verification.confidence is not None)
            else 1.0
        )
        # If text-tier was already very confident in its NO, do not
        # override — that's the dangerous case. The block-threshold
        # (default 0.95) is intentionally well above the LLM verifier's
        # internal cap of 0.85 so vision can win the typical disagreement.
        if verify_conf >= self.visual_block_override_threshold:
            return terminal
        # Vision says yes confidently AND text-tier was unsure.
        # Vision findings that themselves describe a problem
        # (captcha / modal / error) should NOT promote — guard against
        # the LLM saying "ok=true" while the suggested_action says
        # "abort". This only fires when suggested_action is benign.
        sa = (getattr(vf, "suggested_action", "") or "").strip().lower()
        if sa.startswith(("dismiss_modal", "abort", "retry")):
            return terminal
        if record.verification is not None:
            record.verification.ok = True
            record.verification.tier = f"{record.verification.tier}+vision_override"
            extra = (
                f"vision_override(conf={vision_conf:.2f}>{self.visual_override_threshold:.2f}, "
                f"verifier_conf={verify_conf:.2f}<{self.visual_override_threshold:.2f})"
            )
            record.verification.reason = (
                f"{record.verification.reason} | {extra}"
                if record.verification.reason
                else extra
            )
            # Vision is our trusted signal here; raise stored confidence.
            record.verification.confidence = max(
                record.verification.confidence or 0.0, vision_conf
            )
        return "ok"

    # ------------------------------------------------------------------
    # Gap #3 — Synthesise a rewrite proposal from a vision finding.
    # ------------------------------------------------------------------

    def _proposal_from_vision(
        self,
        *,
        record: StepRunRecord,
        step: WorkflowStep,
    ) -> Any | None:
        """Map a vision verdict onto a :class:`WorkflowRewriteProposal`.

        Returns ``None`` when vision saw nothing actionable. We only
        emit proposals when vision is confident *and* its
        ``suggested_action`` begins with a known prefix.
        """
        vf = record.visual_finding
        if vf is None:
            return None
        # Guard against cascading vision-on-vision: if this step is itself
        # a vision-derived dismiss step that just failed, do NOT emit
        # another dismiss. The inserts budget would also stop the loop,
        # but exiting early saves vision-call cost.
        if step.step_id.endswith("__vis_dismiss"):
            return None
        vision_conf = float(getattr(vf, "confidence", 0.0) or 0.0)
        if vision_conf < self.visual_override_threshold:
            return None
        suggestion = (getattr(vf, "suggested_action", "") or "").strip()
        if not suggestion:
            return None

        # Lazy import so non-vision callers don't pay for the cost.
        from xpath_healer.core.workflow import (
            REWRITE_ACTION_ABORT,
            REWRITE_ACTION_INSERT_BEFORE,
            REWRITE_ACTION_SKIP,
            WorkflowRewriteProposal,
            WorkflowStep as _WS,
        )

        sa_lower = suggestion.lower()
        meta = {
            "origin": "vision",
            "vision_finding": str(getattr(vf, "finding", "") or "")[:240],
            "vision_evidence": str(getattr(vf, "evidence", "") or "")[:240],
            "vision_confidence": vision_conf,
        }

        if sa_lower.startswith("abort"):
            return WorkflowRewriteProposal(
                action=REWRITE_ACTION_ABORT,
                reason=f"vision:{suggestion[:120]}",
                confidence=vision_conf,
                auto_applied=True,
                metadata=meta,
            )

        if sa_lower.startswith("dismiss_modal"):
            # Pull the close-button label after the colon if provided.
            label = ""
            if ":" in suggestion:
                label = suggestion.split(":", 1)[1].strip().strip("'\"")
            if not label:
                # Fall back to common defaults — orchestrator will let
                # the heal cascade try several.
                label = "Close"
            new_step = _WS(
                step_id=f"{step.step_id}__vis_dismiss",
                intent=f"dismiss blocking modal so '{step.target_label}' is reachable",
                action="click",
                target_label=label,
                target_kind="button",
                expected_outcome="modal is closed and the underlying page is visible",
                optional=True,
            )
            return WorkflowRewriteProposal(
                action=REWRITE_ACTION_INSERT_BEFORE,
                reason=f"vision saw blocking modal; dismissing via '{label}'",
                confidence=vision_conf,
                new_step=new_step,
                auto_applied=True,
                metadata=meta,
            )

        if sa_lower.startswith("retry") and step.optional:
            # An optional step that vision said transiently missed —
            # safer to skip than to retry blindly.
            return WorkflowRewriteProposal(
                action=REWRITE_ACTION_SKIP,
                reason="vision suggested retry on an optional step",
                confidence=vision_conf,
                auto_applied=True,
                metadata=meta,
            )

        return None

    # ------------------------------------------------------------------
    # Gap #2 — Visual recovery hook for the heal cascade.
    # ------------------------------------------------------------------

    async def _try_visual_candidate_heal(
        self,
        *,
        page: Any,
        step: WorkflowStep,
    ) -> Any | None:
        """Candidate-based vision heal (from "Locator healer eyes" doc).

        Pipeline:
          1. Extract clickable/interactable DOM candidates with their
             visible text, role, aria-label, bounding box, and a stable
             CSS selector.
          2. Take a quick viewport screenshot.
          3. Ask the VisualInspector which candidate matches the step's
             intent (vision LLM grounded in DOM, not raw coords).
          4. Build a Playwright locator from the chosen candidate's
             selector and return it for the executor to drive.

        Returns ``None`` when no candidate matched or pre-conditions
        aren't met (no vision LLM, no page handle, etc.).
        """
        if self.visual_inspector is None:
            return None
        evaluate = getattr(page, "evaluate", None)
        screenshot = getattr(page, "screenshot", None)
        page_locator = getattr(page, "locator", None)
        if not (callable(evaluate) and callable(screenshot) and callable(page_locator)):
            return None
        # Extract candidates via JS.
        try:
            candidates = await evaluate(_CANDIDATE_EXTRACTION_JS)
        except Exception:
            self.logger.exception("candidate extraction failed")
            return None
        if not candidates:
            return None
        # Take a viewport screenshot (full_page=False is cheaper and matches
        # what the user sees, which is what vision needs to ground on).
        import tempfile
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp(prefix="xh_cand_"))
        shot_path = tmp_dir / f"cand_{step.step_id}.png"
        try:
            await screenshot(path=str(shot_path), full_page=False)
        except Exception:
            self.logger.exception("candidate-heal screenshot failed")
            return None
        if not shot_path.exists():
            return None
        intent = (
            f"action={step.action!r} target_label={step.target_label!r} "
            f"intent={step.intent!r}"
        )
        try:
            pick = await self.visual_inspector.pick_candidate(
                intent=intent,
                candidates=candidates,
                screenshot_path=str(shot_path),
            )
        except Exception:
            self.logger.exception("vision pick_candidate raised")
            return None
        if pick.index < 0 or not pick.css_selector:
            self.logger.info(
                "candidate-heal: vision returned no match (reason=%s conf=%.2f)",
                pick.reason, pick.confidence,
            )
            return None
        if pick.confidence < 0.5:
            self.logger.info(
                "candidate-heal: vision picked index=%d but conf=%.2f < 0.5",
                pick.index, pick.confidence,
            )
            return None
        # Build a Playwright locator from the chosen CSS selector.
        try:
            loc = page_locator(pick.css_selector).first
        except Exception:
            self.logger.exception("page.locator(%r) failed", pick.css_selector)
            return None
        self.logger.info(
            "candidate-heal: vision chose index=%d selector=%r reason=%r conf=%.2f",
            pick.index, pick.css_selector, pick.reason, pick.confidence,
        )
        return loc

    async def _try_visual_recovery(
        self,
        *,
        page: Any,
        step: WorkflowStep,
    ) -> tuple[Any | None, Any | None]:
        """When the deterministic + agent + RAG cascade can't find an
        element, take a fresh screenshot and ask vision what is on the
        screen. If vision reports a blocking modal / captcha we emit a
        rewrite proposal; otherwise return ``None``.

        Returns ``(proposal, finding)``. ``finding`` is always the raw
        :class:`InspectionResult` (or ``None`` if vision was not
        invoked) so the caller can stash it on the record and skip a
        duplicate diagnosis call later. ``proposal`` is ``None`` unless
        vision suggested a concrete remediation.

        Cheap to invoke: at most 1 screenshot + 1 vision call. Skipped
        entirely when no inspector is configured, when the policy is
        ``never``, or when the feature is disabled.
        """
        if not self.visual_recovery_enabled:
            return None, None
        if self.visual_inspector is None:
            return None, None
        from xpath_healer.orchestrator.visual import VisualUsagePolicy

        if self.visual_policy == VisualUsagePolicy.NEVER:
            return None, None

        # Take an ad-hoc screenshot. We never need the recorder for this
        # path — but we do need somewhere to write the PNG.
        import tempfile
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp(prefix="xh_vis_rec_"))
        shot_path = tmp_dir / f"recovery_{step.step_id}.png"
        try:
            screenshot = getattr(page, "screenshot", None)
            if callable(screenshot):
                await screenshot(path=str(shot_path), full_page=False)
        except Exception:
            self.logger.exception("visual recovery screenshot failed")
            return None, None
        if not shot_path.exists():
            return None, None

        question = (
            f"The automation tried to {step.action!r} the element "
            f"labelled {step.target_label!r} and could not find it. "
            "Look at the screenshot. Tell me, in JSON: is a modal / popup "
            "/ login wall / cookie banner / captcha blocking the page? "
            "If yes, give its visible close-button label "
            "(suggested_action='dismiss_modal:<label>'). If the site is "
            "refusing bots, set suggested_action='abort:<reason>'. "
            "Otherwise set suggested_action=''."
        )
        try:
            finding = await self.visual_inspector.inspect(
                question=question,
                screenshots=[str(shot_path)],
                max_frames=1,
            )
        except Exception:
            self.logger.exception("visual recovery inspect failed")
            return None, None
        if not getattr(finding, "ok", False):
            return None, finding
        # Reuse the same proposal-synthesis logic — give it a dummy
        # record so we don't change the public signature.
        from xpath_healer.orchestrator.models import StepRunRecord as _Rec

        synthetic = _Rec(step_id=step.step_id, action=step.action, target_label=step.target_label)
        synthetic.visual_finding = finding
        return self._proposal_from_vision(record=synthetic, step=step), finding

    # ------------------------------------------------------------------
    # Rewrite handling
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_stronger_proposal(primary: Any, secondary: Any) -> Any | None:
        """Return whichever proposal is more confident.

        ``primary`` is the rewriter-agent proposal; ``secondary`` is the
        vision-derived proposal. ``None`` for either is a non-vote.
        Ties go to the secondary (vision) on the theory that the agent
        rewriter already decided it had no clue (else we wouldn't have
        consulted vision).
        """
        if primary is None and secondary is None:
            return None
        if primary is None:
            return secondary
        if secondary is None:
            return primary
        pc = float(getattr(primary, "confidence", 0.0) or 0.0)
        sc = float(getattr(secondary, "confidence", 0.0) or 0.0)
        return secondary if sc >= pc else primary

    @staticmethod
    def _handle_rewrite(
        *,
        step: WorkflowStep,
        proposal: Any,
    ) -> tuple[str, str, WorkflowStep | None]:
        """Map a healer rewrite proposal onto an orchestrator terminal.

        Returns ``(terminal, applied, new_step)``. Pure function — the
        caller (``run()``) owns the actual plan mutation.
        """
        if proposal is None:
            return ("fail", "", None)
        action = (getattr(proposal, "action", "") or "").strip().lower()
        if action == REWRITE_ACTION_SKIP:
            if step.optional or getattr(proposal, "auto_applied", False):
                return ("skip", REWRITE_ACTION_SKIP, None)
            return ("fail", REWRITE_ACTION_SKIP, None)
        if action == REWRITE_ACTION_ABORT:
            return ("abort", REWRITE_ACTION_ABORT, None)
        if action == REWRITE_ACTION_INSERT_BEFORE:
            new_step = getattr(proposal, "new_step", None)
            if new_step is None:
                return ("fail", REWRITE_ACTION_INSERT_BEFORE, None)
            return ("insert_before", REWRITE_ACTION_INSERT_BEFORE, new_step)
        if action == REWRITE_ACTION_REPLACE:
            new_step = getattr(proposal, "new_step", None)
            if new_step is None:
                return ("fail", REWRITE_ACTION_REPLACE, None)
            return ("replace", REWRITE_ACTION_REPLACE, new_step)
        return ("fail", action or "unknown_proposal", None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _vars_for(step: WorkflowStep, value: str) -> dict[str, str]:
        out: dict[str, str] = {}
        if step.target_label:
            out["label"] = step.target_label
            out["text"] = step.target_label
            # Some sites carry the same label on multiple elements
            # (e.g. mobile + desktop search boxes). Take the first
            # match instead of rejecting on multiple_matches.
            out["strict_single_match"] = "false"
        if value and step.action in {"fill", "select"}:
            # Some healing strategies use the value as a placeholder
            # disambiguator for textbox/select.
            out["value_hint"] = value
        return out
