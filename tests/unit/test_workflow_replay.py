"""Phase 4c — workflow replay cache.

Tests the ``_workflow_replay_candidates`` stage in isolation. The stage
returns ranked ``CandidateSpec`` entries from the
``workflow_run_repository``; the existing healing pipeline + validator
takes it from there.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from xpath_healer.core.healing_service import HealingService
from xpath_healer.core.models import BuildInput, Intent, LocatorSpec
from xpath_healer.core.workflow import (
    STEP_STATUS_HEAL_FAILED,
    STEP_STATUS_HEAL_SUCCEEDED,
    STEP_STATUS_SKIPPED,
    STEP_STATUS_STEP_FAILED,
    STEP_STATUS_STEP_SUCCEEDED,
    StepRun,
    WorkflowContext,
    WorkflowStep,
)
from xpath_healer.store.workflow_run_repository import InMemoryWorkflowRunRepository


class _FakeCtx:
    """Minimal StrategyContext stub."""

    def __init__(self, repo: object | None) -> None:
        self.workflow_run_repository = repo
        self.logger = logging.getLogger("test.replay")


def _wf_inp(workflow_id: str = "signup", step_id: str = "fill_email") -> BuildInput:
    return BuildInput(
        page=object(),
        app_id="a",
        page_name="signup",
        element_name="email_input",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        intent=Intent(label="Email"),
        workflow_context=WorkflowContext(
            workflow_id=workflow_id,
            workflow_intent="create user",
            current_step=WorkflowStep(
                step_id=step_id,
                intent="email entry",
                action="fill",
                target_label="Email",
            ),
        ),
    )


def _no_wf_inp() -> BuildInput:
    return BuildInput(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={"label": "Email"},
        intent=Intent(label="Email"),
        workflow_context=None,
    )


def _step(
    workflow_id: str,
    step_id: str,
    status: str,
    locator: dict[str, Any] | None = None,
    healer_stage: str = "rules",
) -> StepRun:
    return StepRun(
        workflow_id=workflow_id,
        step_id=step_id,
        status=status,
        locator_used=locator if locator is not None else {},
        healer_stage=healer_stage,
    )


# ---------------------------------------------------------------------------
# Skip conditions — must return [] silently
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_returns_empty_without_workflow_context() -> None:
    service = HealingService(builder=None)
    ctx = _FakeCtx(InMemoryWorkflowRunRepository())
    out = await service._workflow_replay_candidates(ctx, _no_wf_inp())
    assert out == []


@pytest.mark.asyncio
async def test_replay_returns_empty_without_repo() -> None:
    service = HealingService(builder=None)
    ctx = _FakeCtx(repo=None)
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert out == []


@pytest.mark.asyncio
async def test_replay_returns_empty_when_no_history_exists() -> None:
    service = HealingService(builder=None)
    repo = InMemoryWorkflowRunRepository()
    ctx = _FakeCtx(repo)
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert out == []


@pytest.mark.asyncio
async def test_replay_returns_empty_when_repo_raises() -> None:
    class _BoomRepo:
        async def find_step_history(self, *a, **kw):
            raise RuntimeError("disk gone")

    service = HealingService(builder=None)
    ctx = _FakeCtx(_BoomRepo())
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert out == []


# ---------------------------------------------------------------------------
# Happy paths — trust tiers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_returns_step_succeeded_record_with_high_score() -> None:
    repo = InMemoryWorkflowRunRepository()
    await repo.record_step(
        _step(
            "signup",
            "fill_email",
            STEP_STATUS_STEP_SUCCEEDED,
            locator={"kind": "xpath", "value": "//*[@id='email']"},
            healer_stage="rules",
        )
    )
    service = HealingService(builder=None)
    ctx = _FakeCtx(repo)
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert len(out) == 1
    cand = out[0]
    assert cand.strategy_id == "workflow_replay"
    assert cand.stage == "workflow_replay"
    assert cand.locator.kind == "xpath"
    assert cand.locator.value == "//*[@id='email']"
    assert cand.score == 0.95
    assert cand.details["trust_tier"] == "step_succeeded"
    assert cand.details["workflow_id"] == "signup"
    assert cand.details["step_id"] == "fill_email"
    assert cand.details["healer_stage"] == "rules"


@pytest.mark.asyncio
async def test_replay_returns_heal_succeeded_record_with_medium_score() -> None:
    repo = InMemoryWorkflowRunRepository()
    await repo.record_step(
        _step(
            "signup",
            "fill_email",
            STEP_STATUS_HEAL_SUCCEEDED,
            locator={"kind": "xpath", "value": "//*[@id='email']"},
        )
    )
    service = HealingService(builder=None)
    ctx = _FakeCtx(repo)
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert len(out) == 1
    assert out[0].score == 0.70
    assert out[0].details["trust_tier"] == "heal_succeeded"


@pytest.mark.asyncio
async def test_replay_skips_failed_and_skipped_records() -> None:
    repo = InMemoryWorkflowRunRepository()
    for status in (STEP_STATUS_HEAL_FAILED, STEP_STATUS_STEP_FAILED, STEP_STATUS_SKIPPED):
        await repo.record_step(
            _step(
                "signup",
                "fill_email",
                status,
                locator={"kind": "xpath", "value": f"//{status}"},
            )
        )
    service = HealingService(builder=None)
    ctx = _FakeCtx(repo)
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert out == []


@pytest.mark.asyncio
async def test_replay_orders_by_score_desc_step_succeeded_before_heal() -> None:
    repo = InMemoryWorkflowRunRepository()
    # Record in mixed order to ensure ordering comes from sorting, not insertion.
    await repo.record_step(
        _step(
            "signup",
            "fill_email",
            STEP_STATUS_HEAL_SUCCEEDED,
            locator={"kind": "xpath", "value": "//heal"},
        )
    )
    await repo.record_step(
        _step(
            "signup",
            "fill_email",
            STEP_STATUS_STEP_SUCCEEDED,
            locator={"kind": "xpath", "value": "//step"},
        )
    )
    service = HealingService(builder=None)
    ctx = _FakeCtx(repo)
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert [c.locator.value for c in out] == ["//step", "//heal"]


@pytest.mark.asyncio
async def test_replay_dedupes_identical_locators_across_runs() -> None:
    repo = InMemoryWorkflowRunRepository()
    for _ in range(3):
        await repo.record_step(
            _step(
                "signup",
                "fill_email",
                STEP_STATUS_STEP_SUCCEEDED,
                locator={"kind": "xpath", "value": "//*[@id='email']"},
            )
        )
    service = HealingService(builder=None)
    ctx = _FakeCtx(repo)
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert len(out) == 1


@pytest.mark.asyncio
async def test_replay_bounds_returned_candidates_to_three() -> None:
    repo = InMemoryWorkflowRunRepository()
    for i in range(6):
        await repo.record_step(
            _step(
                "signup",
                "fill_email",
                STEP_STATUS_STEP_SUCCEEDED,
                locator={"kind": "xpath", "value": f"//*[@id='e{i}']"},
            )
        )
    service = HealingService(builder=None)
    ctx = _FakeCtx(repo)
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert len(out) == 3


@pytest.mark.asyncio
async def test_replay_skips_records_with_unusable_locator_payloads() -> None:
    repo = InMemoryWorkflowRunRepository()
    await repo.record_step(
        _step("signup", "fill_email", STEP_STATUS_STEP_SUCCEEDED, locator={})
    )
    await repo.record_step(
        _step(
            "signup",
            "fill_email",
            STEP_STATUS_STEP_SUCCEEDED,
            locator={"kind": "xpath"},  # value missing
        )
    )
    await repo.record_step(
        _step(
            "signup",
            "fill_email",
            STEP_STATUS_STEP_SUCCEEDED,
            locator={"kind": "xpath", "value": "//*[@id='good']"},
        )
    )
    service = HealingService(builder=None)
    ctx = _FakeCtx(repo)
    out = await service._workflow_replay_candidates(ctx, _wf_inp())
    assert len(out) == 1
    assert out[0].locator.value == "//*[@id='good']"
