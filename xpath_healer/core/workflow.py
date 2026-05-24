"""Workflow data model for Phase 4 (workflow-aware healing).

A ``WorkflowContext`` is what an *outer* agent (the workflow runner)
passes to :meth:`BaseHealerFacade.recover_workflow_step` when healing
one step of a multi-step flow. It is intentionally minimal: just enough
shape so the deterministic stages and the MCP exploratory agent can use
the **intent of the sequence** instead of trying to heal a step in
isolation.

Design rules (carried from the product philosophy discussion):

1. **Deterministic + RAG + agent + agentic hybrid stays intact.**
   ``WorkflowContext`` is an additive enrichment — it is read by stages
   that already exist; no stage is bypassed.
2. **Healer never sequences.** Workflow execution is the outer agent's
   job. This module only carries *passive* context; nothing here
   advances steps, rolls back transactions, or rewrites the workflow on
   its own.
3. **Cheap by default.** The data is small (no DOM snapshots, no
   screenshots) — fits comfortably in an LLM prompt and in JSON storage
   for Phase 4b's run history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class WorkflowStep:
    """One step the outer agent is trying to execute.

    Fields mirror what a workflow YAML / agent plan would carry:
    a human-readable intent, the action verb (``fill``, ``click``,
    ``select``...), the visible target label, and the field family.
    """

    step_id: str
    intent: str
    action: str
    target_label: str = ""
    target_kind: str = ""
    expected_outcome: str = ""
    optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "intent": self.intent,
            "action": self.action,
            "target_label": self.target_label,
            "target_kind": self.target_kind,
            "expected_outcome": self.expected_outcome,
            "optional": self.optional,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkflowStep:
        return cls(
            step_id=str(payload.get("step_id") or ""),
            intent=str(payload.get("intent") or ""),
            action=str(payload.get("action") or ""),
            target_label=str(payload.get("target_label") or ""),
            target_kind=str(payload.get("target_kind") or ""),
            expected_outcome=str(payload.get("expected_outcome") or ""),
            optional=bool(payload.get("optional") or False),
        )


@dataclass(slots=True)
class StepOutcome:
    """Result of a step the outer agent already executed.

    Used by the healer to reason about what state the page is in *before*
    the failing step. ``locator_used`` lets the healer recall the
    selector that worked for the prior step (helpful when the broken
    step is a sibling/descendant).
    """

    step_id: str
    status: str  # "success" | "skipped" | "failed"
    locator_used: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status,
            "locator_used": self.locator_used,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StepOutcome:
        return cls(
            step_id=str(payload.get("step_id") or ""),
            status=str(payload.get("status") or "unknown"),
            locator_used=str(payload.get("locator_used") or ""),
            note=str(payload.get("note") or ""),
        )


# Keys that strongly imply the caller is reasoning about a workflow but
# routed to the locator-only API. Used by ``BaseHealerFacade`` to log a
# misuse warning so future callers don't silently bypass workflow-aware
# healing.
WORKFLOW_SHAPED_VAR_KEYS = frozenset(
    {
        "workflow_id",
        "workflow_intent",
        "step_id",
        "step_index",
        "prior_step_id",
        "prior_step_outcome",
        "next_step_id",
    }
)


@dataclass(slots=True)
class WorkflowContext:
    """Snapshot of the workflow surrounding a single broken step.

    Passed by the outer agent into
    :meth:`BaseHealerFacade.recover_workflow_step`. The healer reads it
    for:

    * **MCP prompt enrichment** — the explorer's user prompt includes
      ``workflow_intent``, ``current_step``, recent ``prior_steps``, and
      ``next_step_hint`` so the agent reasons about the step in context.
    * **Deterministic anchor hints** — strategies that key off label
      text can use ``current_step.target_label`` even if ``vars`` lacks
      ``label``.
    * **Future replay cache (4c)** — the key includes ``workflow_id``
      and ``current_step.step_id``.
    """

    workflow_id: str
    workflow_intent: str
    current_step: WorkflowStep
    # Recent step outcomes — keep small (the outer agent should trim to
    # the last ~5) so prompt cost stays bounded.
    prior_steps: list[StepOutcome] = field(default_factory=list)
    # Optional next-step description so the agent can avoid actions that
    # would invalidate the upcoming step.
    next_step_hint: WorkflowStep | None = None
    # Free-form per-workflow metadata (locale, role, feature flags).
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "workflow_intent": self.workflow_intent,
            "current_step": self.current_step.to_dict(),
            "prior_steps": [s.to_dict() for s in self.prior_steps],
            "next_step_hint": self.next_step_hint.to_dict() if self.next_step_hint else None,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkflowContext:
        next_hint_raw = payload.get("next_step_hint")
        created_raw = payload.get("created_at")
        return cls(
            workflow_id=str(payload.get("workflow_id") or ""),
            workflow_intent=str(payload.get("workflow_intent") or ""),
            current_step=WorkflowStep.from_dict(dict(payload.get("current_step") or {})),
            prior_steps=[
                StepOutcome.from_dict(s)
                for s in list(payload.get("prior_steps") or [])
                if isinstance(s, dict)
            ],
            next_step_hint=WorkflowStep.from_dict(dict(next_hint_raw)) if isinstance(next_hint_raw, dict) else None,
            metadata=dict(payload.get("metadata") or {}),
            created_at=(
                datetime.fromisoformat(created_raw)
                if isinstance(created_raw, str)
                else datetime.now(UTC)
            ),
        )


# ---------------------------------------------------------------------------
# Phase 4b — workflow run history (persistence + recording)
#
# Two-tier event semantics:
#   * heal_succeeded / heal_failed  — recorded by recover_workflow_step
#                                     immediately, knows only locator status.
#   * step_succeeded / step_failed  — set by the outer agent via
#                                     report_step_outcome AFTER attempting
#                                     the actual UI action; upgrades or
#                                     downgrades a heal_succeeded record.
# Phase 4c's replay cache will only trust step_succeeded records.
# ---------------------------------------------------------------------------


# Canonical status values. Keep this small — adding values means cache
# semantics change and Phase 4c must learn about them.
STEP_STATUS_HEAL_SUCCEEDED = "heal_succeeded"
STEP_STATUS_HEAL_FAILED = "heal_failed"
STEP_STATUS_STEP_SUCCEEDED = "step_succeeded"
STEP_STATUS_STEP_FAILED = "step_failed"
STEP_STATUS_SKIPPED = "skipped"


@dataclass(slots=True)
class StepRun:
    """One step's outcome inside a workflow run.

    The healer writes this with ``status=heal_succeeded`` (or
    ``heal_failed``) the moment recovery returns. The outer agent may
    later call ``report_step_outcome`` which UPDATES the same record's
    status to ``step_succeeded`` / ``step_failed`` based on whether the
    UI action actually worked.
    """

    workflow_id: str
    step_id: str
    status: str
    locator_used: dict[str, Any] = field(default_factory=dict)
    healer_stage: str = ""
    page_signature_hash: str = ""
    duration_ms: float | None = None
    failure_reason: str = ""
    note: str = ""
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "status": self.status,
            "locator_used": dict(self.locator_used),
            "healer_stage": self.healer_stage,
            "page_signature_hash": self.page_signature_hash,
            "duration_ms": self.duration_ms,
            "failure_reason": self.failure_reason,
            "note": self.note,
            "recorded_at": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StepRun:
        recorded_raw = payload.get("recorded_at")
        return cls(
            workflow_id=str(payload.get("workflow_id") or ""),
            step_id=str(payload.get("step_id") or ""),
            status=str(payload.get("status") or ""),
            locator_used=dict(payload.get("locator_used") or {}),
            healer_stage=str(payload.get("healer_stage") or ""),
            page_signature_hash=str(payload.get("page_signature_hash") or ""),
            duration_ms=payload.get("duration_ms"),
            failure_reason=str(payload.get("failure_reason") or ""),
            note=str(payload.get("note") or ""),
            recorded_at=(
                datetime.fromisoformat(recorded_raw)
                if isinstance(recorded_raw, str)
                else datetime.now(UTC)
            ),
        )


REWRITE_ACTION_SKIP = "skip"
REWRITE_ACTION_ABORT = "abort"
REWRITE_ACTION_INSERT_BEFORE = "insert_before"
REWRITE_ACTION_REPLACE = "replace"

# All currently-supported actions. ``insert_before`` and ``replace``
# both require ``WorkflowRewriteProposal.new_step`` to be populated with
# a fully-specified ``WorkflowStep``; ``skip`` and ``abort`` do not.
_SUPPORTED_REWRITE_ACTIONS = frozenset(
    {
        REWRITE_ACTION_SKIP,
        REWRITE_ACTION_ABORT,
        REWRITE_ACTION_INSERT_BEFORE,
        REWRITE_ACTION_REPLACE,
    }
)
_ACTIONS_REQUIRING_NEW_STEP = frozenset(
    {REWRITE_ACTION_INSERT_BEFORE, REWRITE_ACTION_REPLACE}
)


@dataclass(slots=True)
class WorkflowRewriteProposal:
    """Returned by the rewrite agent when the locator cascade fails.

    The healer never auto-executes proposals on its own. With an
    :class:`AutoApplyPolicy` configured by the outer agent, the healer
    may set :attr:`auto_applied` to ``True`` when the proposal meets
    *the outer agent's own* policy — but execution still belongs to
    the caller. Auto-applied just means "this met your bar."

    Supported actions:
      * ``skip`` / ``abort`` — no ``new_step`` required
      * ``insert_before`` / ``replace`` — ``new_step`` MUST be a fully
        specified :class:`WorkflowStep` the outer agent can execute
    """

    action: str
    reason: str = ""
    confidence: float = 0.0
    new_step: WorkflowStep | None = None
    # Set by the facade after running the proposal through an
    # :class:`AutoApplyPolicy`. ``False`` by default; ``True`` only
    # when the caller's own policy permits it.
    auto_applied: bool = False
    # Free-form provenance — model name, rounds used, etc.
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "confidence": self.confidence,
            "new_step": self.new_step.to_dict() if self.new_step else None,
            "auto_applied": self.auto_applied,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkflowRewriteProposal:
        new_step_raw = payload.get("new_step")
        return cls(
            action=str(payload.get("action") or ""),
            reason=str(payload.get("reason") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            new_step=WorkflowStep.from_dict(dict(new_step_raw)) if isinstance(new_step_raw, dict) else None,
            auto_applied=bool(payload.get("auto_applied") or False),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class AutoApplyPolicy:
    """Outer-agent policy that gates ``auto_applied=True`` on proposals.

    The healer never runs the rewrite; this just signals whether the
    caller's own rules would consider it safe. Default values are
    intentionally conservative — opt in explicitly.
    """

    # Which actions are ever eligible for auto-apply. Empty means none.
    allowed_actions: frozenset[str] = field(default_factory=frozenset)
    # Confidence floor (0.0–1.0) the proposal must exceed.
    min_confidence: float = 0.95
    # How many prior confirmed-success runs of the same proposed action
    # for the same (workflow_id, step_id) are required. ``0`` means no
    # historical confirmation needed.
    min_prior_confirmations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_actions": sorted(self.allowed_actions),
            "min_confidence": self.min_confidence,
            "min_prior_confirmations": self.min_prior_confirmations,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AutoApplyPolicy:
        actions = payload.get("allowed_actions") or []
        return cls(
            allowed_actions=frozenset(str(a) for a in actions if a),
            min_confidence=float(payload.get("min_confidence") or 0.95),
            min_prior_confirmations=int(payload.get("min_prior_confirmations") or 0),
        )

    @classmethod
    def disabled(cls) -> AutoApplyPolicy:
        """Convenience: a policy that auto-applies nothing."""
        return cls(allowed_actions=frozenset(), min_confidence=2.0)


def is_mvp_rewrite_action(action: str) -> bool:
    """Back-compat shim — now equivalent to is_supported_rewrite_action.

    Kept so any external callers that imported the original 4c MVP
    helper keep working. Prefer :func:`is_supported_rewrite_action` in
    new code.
    """
    return is_supported_rewrite_action(action)


def is_supported_rewrite_action(action: str) -> bool:
    return (action or "").strip().lower() in _SUPPORTED_REWRITE_ACTIONS


def action_requires_new_step(action: str) -> bool:
    return (action or "").strip().lower() in _ACTIONS_REQUIRING_NEW_STEP


@dataclass(slots=True)
class WorkflowRun:
    """An ordered append-log of step outcomes for one workflow execution.

    Phase 4b stores one ``WorkflowRun`` per workflow_id and retains up to
    ``max_steps`` recent entries (eviction is the repo's responsibility,
    not this dataclass's). Phase 4c will query these to seed the replay
    cache.
    """

    workflow_id: str
    steps: list[StepRun] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "steps": [s.to_dict() for s in self.steps],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkflowRun:
        steps_raw = payload.get("steps") or []
        return cls(
            workflow_id=str(payload.get("workflow_id") or ""),
            steps=[StepRun.from_dict(s) for s in steps_raw if isinstance(s, dict)],
            metadata=dict(payload.get("metadata") or {}),
        )
