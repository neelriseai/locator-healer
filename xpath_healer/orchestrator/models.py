"""Data models for the workflow orchestrator (Phase 6).

Kept minimal. ``WorkflowStep`` already exists in
``xpath_healer.core.workflow``; we add one field (``value``) below by
extension rather than touching the existing dataclass — additive only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from xpath_healer.core.workflow import WorkflowStep


@dataclass(slots=True)
class WorkflowGoal:
    """Outer-agent intent expressed in natural language.

    ``constraints`` is a free-form dict for caller-specific limits
    (max_steps, time_budget_s, allowed_actions, ...). The
    orchestrator reads only the keys it knows; unknown keys are
    passed through to decomposer prompt for context.
    """

    text: str
    start_url: str = ""
    # Allowed values that the goal references explicitly (email, query
    # text, password). The decomposer wires these into the matching
    # WorkflowStep.value so the executor knows what to fill / select.
    values: dict[str, str] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)

    def cache_key(self) -> str:
        """Stable hash for plan caching (Phase 6c)."""
        canonical = "|".join(
            [
                (self.text or "").strip().lower(),
                (self.start_url or "").strip().lower(),
                "values=" + ",".join(f"{k}={v}" for k, v in sorted(self.values.items())),
            ]
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class PlannedWorkflow:
    """Output of GoalDecomposer.

    ``steps`` are :class:`WorkflowStep`s extended with ``value`` /
    ``selector_hints`` that the orchestrator threads into healing and
    execution. ``metadata`` captures decomposer provenance (model used,
    tokens, page outline size, etc.).
    """

    workflow_id: str
    goal: WorkflowGoal
    steps: list[WorkflowStep] = field(default_factory=list)
    # value-per-step keyed by step_id (decomposer fills this); kept
    # outside WorkflowStep to avoid touching the existing dataclass.
    values_by_step: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def value_for(self, step_id: str) -> str:
        return self.values_by_step.get(step_id, "")


# Canonical ``WorkflowStep.action`` values the orchestrator understands.
ACTION_NAVIGATE = "navigate"
ACTION_FILL = "fill"
ACTION_CLICK = "click"
ACTION_SELECT = "select"
ACTION_VERIFY = "verify"          # read-only — verifier only
ACTION_EXTRACT = "extract"        # read-only — structured data pull from a LIST
ACTION_EXTRACT_RECORD = "extract_record"  # read-only — ONE record from the page (PDP)
ACTION_PRESS_KEY = "press_key"    # keyboard input (Enter, Escape, Tab, ArrowDown...)
ACTION_WAIT = "wait"              # wait for element / timeout / network idle
ACTION_SCROLL = "scroll"          # scroll element into view, or page bottom
ACTION_HOVER = "hover"            # mouse hover for dropdowns / tooltips
ACTION_SCREENSHOT = "screenshot"  # snapshot artifact for proof / debugging

_KNOWN_ACTIONS = frozenset(
    {
        ACTION_NAVIGATE, ACTION_FILL, ACTION_CLICK, ACTION_SELECT,
        ACTION_VERIFY, ACTION_EXTRACT, ACTION_EXTRACT_RECORD,
        ACTION_PRESS_KEY, ACTION_WAIT,
        ACTION_SCROLL, ACTION_HOVER, ACTION_SCREENSHOT,
    }
)


def is_known_action(action: str) -> bool:
    return (action or "").strip().lower() in _KNOWN_ACTIONS


@dataclass(slots=True)
class ExecutionResult:
    """What ActionExecutor returns after attempting one step.

    ``status`` is one of:
      * ``"ok"``       — action completed without raising
      * ``"error"``    — action raised (locator stale, click intercepted)
      * ``"skipped"``  — orchestrator chose to skip the step (optional)
    """

    status: str
    action: str
    detail: str = ""
    # Free-form post-action page hints the verifier can use cheaply
    # (e.g. {"url_after": "...", "inner_text_after": "..."} or
    # {"value_after": "alice@example.com"}).
    page_signal: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerificationResult:
    """What OutcomeVerifier returns.

    ``tier`` identifies which path the verifier took so we can audit
    cost: ``"auto"`` (free), ``"structural"`` (free DOM check) or
    ``"llm"`` (one chat call).
    """

    ok: bool
    tier: str
    reason: str = ""
    confidence: float = 1.0


@dataclass(slots=True)
class StepRunRecord:
    """Per-step telemetry the orchestrator emits in the final result."""

    step_id: str
    action: str
    target_label: str
    heal_status: str = ""
    heal_strategy: str = ""
    locator_kind: str = ""
    locator_value: str = ""
    execution: ExecutionResult | None = None
    verification: VerificationResult | None = None
    rewrite_applied: str = ""  # skip/abort/insert_before/replace or empty
    duration_ms: float | None = None
    # Phase 7: optional vision finding attached to this step. Typed as
    # ``Any`` to avoid importing visual.InspectionResult here.
    visual_finding: Any = None


@dataclass(slots=True)
class OrchestrationResult:
    """Final result returned by WorkflowOrchestrator.run().

    ``status`` is one of:
      * ``"success"`` — every required step succeeded (skipped steps OK)
      * ``"failed"``  — a required step's recovery exhausted all options
      * ``"aborted"`` — rewrite agent emitted abort, orchestrator honoured
    """

    status: str
    goal: WorkflowGoal
    plan: PlannedWorkflow | None = None
    completed_steps: list[StepRunRecord] = field(default_factory=list)
    failed_step: StepRunRecord | None = None
    # Aggregated structured output from any ``extract`` steps. Keyed
    # by ``WorkflowStep.step_id`` → list of per-item dicts.
    extracted_data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
