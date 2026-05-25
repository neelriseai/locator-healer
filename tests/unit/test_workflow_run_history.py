"""Phase 4b — workflow run history (data model, repos, auto-record).

Three coarse test groups:

* model round-trip (``StepRun``, ``WorkflowRun``)
* repository contract — exercised against BOTH ``InMemoryWorkflowRunRepository``
  and ``JsonWorkflowRunRepository`` via the same parametrised tests
* facade integration — ``recover_workflow_step`` auto-records the heal
  outcome, ``report_step_outcome`` upgrades a heal_* record to step_*
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from xpath_healer.api.base import BaseHealerFacade
from xpath_healer.core.models import LocatorSpec, Recovered
from xpath_healer.core.workflow import (
    STEP_STATUS_HEAL_FAILED,
    STEP_STATUS_HEAL_SUCCEEDED,
    STEP_STATUS_STEP_FAILED,
    STEP_STATUS_STEP_SUCCEEDED,
    StepRun,
    WorkflowContext,
    WorkflowRun,
    WorkflowStep,
)
from xpath_healer.store.workflow_run_repository import (
    InMemoryWorkflowRunRepository,
    JsonWorkflowRunRepository,
    WorkflowRunRepository,
    safe_record_step,
    safe_update_step_status,
)


# ---------------------------------------------------------------------------
# Model round-trip
# ---------------------------------------------------------------------------


def test_step_run_round_trip() -> None:
    s = StepRun(
        workflow_id="signup",
        step_id="s1",
        status=STEP_STATUS_HEAL_SUCCEEDED,
        locator_used={"kind": "xpath", "value": "//x"},
        healer_stage="rules",
        page_signature_hash="abc123",
        duration_ms=12.5,
        failure_reason="",
        note="ok",
    )
    revived = StepRun.from_dict(s.to_dict())
    assert revived.workflow_id == s.workflow_id
    assert revived.step_id == s.step_id
    assert revived.status == s.status
    assert revived.locator_used == s.locator_used
    assert revived.healer_stage == s.healer_stage
    assert revived.page_signature_hash == s.page_signature_hash
    assert revived.duration_ms == s.duration_ms
    assert revived.note == s.note


def test_workflow_run_round_trip() -> None:
    run = WorkflowRun(
        workflow_id="w",
        steps=[
            StepRun(workflow_id="w", step_id="s1", status=STEP_STATUS_HEAL_SUCCEEDED),
            StepRun(workflow_id="w", step_id="s2", status=STEP_STATUS_STEP_FAILED),
        ],
        metadata={"locale": "en-US"},
    )
    revived = WorkflowRun.from_dict(run.to_dict())
    assert revived.workflow_id == run.workflow_id
    assert [s.step_id for s in revived.steps] == ["s1", "s2"]
    assert revived.metadata == run.metadata


# ---------------------------------------------------------------------------
# Repository contract — parametrised across both impls
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_repo() -> InMemoryWorkflowRunRepository:
    return InMemoryWorkflowRunRepository(max_steps_per_workflow=5)


@pytest.fixture
def json_repo(tmp_path: Path) -> JsonWorkflowRunRepository:
    return JsonWorkflowRunRepository(tmp_path / "wfruns", max_steps_per_workflow=5)


@pytest.fixture(params=["mem", "json"])
def any_repo(request, in_memory_repo, json_repo) -> WorkflowRunRepository:
    return in_memory_repo if request.param == "mem" else json_repo


def _step(wid: str = "w", sid: str = "s1", status: str = STEP_STATUS_HEAL_SUCCEEDED) -> StepRun:
    return StepRun(workflow_id=wid, step_id=sid, status=status)


@pytest.mark.asyncio
async def test_record_step_and_get_run(any_repo: WorkflowRunRepository) -> None:
    await any_repo.record_step(_step("w1", "s1"))
    await any_repo.record_step(_step("w1", "s2"))
    run = await any_repo.get_run("w1")
    assert run is not None
    assert [s.step_id for s in run.steps] == ["s1", "s2"]


@pytest.mark.asyncio
async def test_get_run_returns_none_for_unknown_workflow(
    any_repo: WorkflowRunRepository,
) -> None:
    assert await any_repo.get_run("never_seen") is None


@pytest.mark.asyncio
async def test_retention_cap_evicts_oldest(any_repo: WorkflowRunRepository) -> None:
    # Cap is 5 (fixture). Insert 7; expect last 5 (s3..s7) retained.
    for i in range(7):
        await any_repo.record_step(_step("w1", f"s{i + 1}"))
    run = await any_repo.get_run("w1")
    assert run is not None
    assert [s.step_id for s in run.steps] == ["s3", "s4", "s5", "s6", "s7"]


@pytest.mark.asyncio
async def test_find_step_history_returns_most_recent_first(
    any_repo: WorkflowRunRepository,
) -> None:
    for i in range(3):
        await any_repo.record_step(
            StepRun(workflow_id="w1", step_id="s1", status=STEP_STATUS_HEAL_SUCCEEDED, note=f"v{i}")
        )
    history = await any_repo.find_step_history("w1", "s1", limit=10)
    assert [s.note for s in history] == ["v2", "v1", "v0"]


@pytest.mark.asyncio
async def test_find_step_history_respects_limit(
    any_repo: WorkflowRunRepository,
) -> None:
    for i in range(4):
        await any_repo.record_step(_step("w1", "s1"))
    history = await any_repo.find_step_history("w1", "s1", limit=2)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_update_step_status_upgrades_most_recent_heal_record(
    any_repo: WorkflowRunRepository,
) -> None:
    await any_repo.record_step(_step("w1", "s1", STEP_STATUS_HEAL_SUCCEEDED))
    await any_repo.record_step(_step("w1", "s1", STEP_STATUS_HEAL_SUCCEEDED))
    updated = await any_repo.update_step_status(
        "w1", "s1", STEP_STATUS_STEP_SUCCEEDED, note="action ok"
    )
    assert updated is True
    history = await any_repo.find_step_history("w1", "s1", limit=2)
    # Most recent matching heal_* record was upgraded.
    assert history[0].status == STEP_STATUS_STEP_SUCCEEDED
    assert history[0].note == "action ok"
    assert history[1].status == STEP_STATUS_HEAL_SUCCEEDED


@pytest.mark.asyncio
async def test_update_step_status_returns_false_when_no_heal_record(
    any_repo: WorkflowRunRepository,
) -> None:
    assert (
        await any_repo.update_step_status("never", "s1", STEP_STATUS_STEP_SUCCEEDED)
    ) is False


@pytest.mark.asyncio
async def test_update_step_status_only_upgrades_heal_records(
    any_repo: WorkflowRunRepository,
) -> None:
    """Already-final records (step_succeeded/failed) must not be modified."""
    await any_repo.record_step(_step("w1", "s1", STEP_STATUS_STEP_SUCCEEDED))
    assert (
        await any_repo.update_step_status("w1", "s1", STEP_STATUS_STEP_FAILED)
    ) is False
    history = await any_repo.find_step_history("w1", "s1", limit=1)
    assert history[0].status == STEP_STATUS_STEP_SUCCEEDED


# ---------------------------------------------------------------------------
# JSON-specific: atomic writes, path safety, persistence across instances
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_repo_persists_across_instances(tmp_path: Path) -> None:
    base = tmp_path / "runs"
    repo1 = JsonWorkflowRunRepository(base, max_steps_per_workflow=10)
    await repo1.record_step(_step("signup", "fill_email"))
    repo2 = JsonWorkflowRunRepository(base, max_steps_per_workflow=10)
    history = await repo2.find_step_history("signup", "fill_email", limit=10)
    assert len(history) == 1
    assert history[0].step_id == "fill_email"


@pytest.mark.asyncio
async def test_json_repo_sanitises_path_traversal_in_workflow_id(
    tmp_path: Path,
) -> None:
    base = tmp_path / "runs"
    repo = JsonWorkflowRunRepository(base, max_steps_per_workflow=10)
    await repo.record_step(_step("../../etc/passwd", "s1"))
    # File must be under base, not anywhere else.
    files = list(base.glob("*.json"))
    assert len(files) == 1
    assert files[0].parent == base
    assert ".." not in files[0].name
    assert "/" not in files[0].name


@pytest.mark.asyncio
async def test_json_repo_recovers_from_corrupt_file(tmp_path: Path) -> None:
    base = tmp_path / "runs"
    base.mkdir(parents=True, exist_ok=True)
    # Pre-write a corrupt file under the slugified workflow_id name.
    (base / "wbad.json").write_text("{ this is not json", encoding="utf-8")
    repo = JsonWorkflowRunRepository(base, max_steps_per_workflow=10)
    # record_step must NOT raise even though existing file is bad.
    await repo.record_step(_step("wbad", "s1"))
    history = await repo.find_step_history("wbad", "s1", limit=5)
    assert len(history) == 1


# ---------------------------------------------------------------------------
# Concurrency — no lost writes under per-workflow lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_records_to_same_workflow_are_serialised(
    in_memory_repo: InMemoryWorkflowRunRepository,
) -> None:
    async def append(i: int) -> None:
        await in_memory_repo.record_step(_step("w1", f"s{i:03d}"))

    # 4 concurrent writers, repo cap is 5 → keep last 5.
    await asyncio.gather(*(append(i) for i in range(4)))
    run = await in_memory_repo.get_run("w1")
    assert run is not None
    assert sorted(s.step_id for s in run.steps) == ["s000", "s001", "s002", "s003"]


# ---------------------------------------------------------------------------
# safe_* helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_record_step_no_op_when_repo_is_none() -> None:
    # Must not raise.
    await safe_record_step(None, _step("w", "s"))


@pytest.mark.asyncio
async def test_safe_update_step_status_returns_false_when_repo_is_none() -> None:
    assert (
        await safe_update_step_status(None, workflow_id="w", step_id="s", new_status="x")
    ) is False


@pytest.mark.asyncio
async def test_safe_helpers_swallow_repo_exceptions() -> None:
    class _BoomRepo:
        async def record_step(self, step_run):
            raise RuntimeError("disk full")

        async def update_step_status(self, *a, **kw):
            raise RuntimeError("disk full")

    repo = _BoomRepo()
    await safe_record_step(repo, _step("w", "s"))  # must not raise
    assert (
        await safe_update_step_status(repo, workflow_id="w", step_id="s", new_status="x")
    ) is False


# ---------------------------------------------------------------------------
# Facade integration — auto-record + report_step_outcome
# ---------------------------------------------------------------------------


class _RecordingFacade(BaseHealerFacade):
    """Bypass BaseHealerFacade.__init__ so the test stays hermetic but
    keeps the auto-record + report_step_outcome wiring under test."""

    def __init__(self, *, recovered: Recovered, repo: WorkflowRunRepository | None) -> None:
        self.logger = logging.getLogger("test.recording_facade")
        self.workflow_run_repository = repo
        self.ctx = None

        class _FakeHealing:
            def __init__(self, recovered: Recovered) -> None:
                self._recovered = recovered

            async def recover_locator(self, ctx, build_input):
                return self._recovered

        self.healing_service = _FakeHealing(recovered)


def _wf_context() -> WorkflowContext:
    return WorkflowContext(
        workflow_id="signup",
        workflow_intent="create user",
        current_step=WorkflowStep(
            step_id="fill_email",
            intent="email entry",
            action="fill",
            target_label="Email",
        ),
    )


@pytest.mark.asyncio
async def test_recover_workflow_step_auto_records_heal_succeeded() -> None:
    repo = InMemoryWorkflowRunRepository(max_steps_per_workflow=10)
    rec = Recovered(
        status="success",
        correlation_id="c1",
        locator_spec=LocatorSpec(kind="xpath", value="//*[@id='email']"),
        strategy_id="rules",
    )
    facade = _RecordingFacade(recovered=rec, repo=repo)
    await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="signup",
        element_name="email_input",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
    )
    history = await repo.find_step_history("signup", "fill_email", limit=5)
    assert len(history) == 1
    rec_step = history[0]
    assert rec_step.status == STEP_STATUS_HEAL_SUCCEEDED
    assert rec_step.locator_used == {"kind": "xpath", "value": "//*[@id='email']", "options": {}, "scope": None}
    assert rec_step.healer_stage == "rules"
    assert rec_step.duration_ms is not None
    assert rec_step.duration_ms >= 0.0


@pytest.mark.asyncio
async def test_recover_workflow_step_auto_records_heal_failed() -> None:
    repo = InMemoryWorkflowRunRepository(max_steps_per_workflow=10)
    rec = Recovered(
        status="failed",
        correlation_id="c1",
        locator_spec=None,
        error="All healing stages failed.",
    )
    facade = _RecordingFacade(recovered=rec, repo=repo)
    await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="signup",
        element_name="email_input",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
    )
    history = await repo.find_step_history("signup", "fill_email", limit=5)
    assert len(history) == 1
    assert history[0].status == STEP_STATUS_HEAL_FAILED
    assert history[0].failure_reason == "All healing stages failed."
    assert history[0].locator_used == {}


@pytest.mark.asyncio
async def test_recover_workflow_step_no_op_recording_when_repo_disabled() -> None:
    facade = _RecordingFacade(
        recovered=Recovered(status="success", correlation_id="c"),
        repo=None,
    )
    # Must not raise even with no repo.
    await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
    )


@pytest.mark.asyncio
async def test_report_step_outcome_upgrades_heal_succeeded_to_step_succeeded() -> None:
    repo = InMemoryWorkflowRunRepository(max_steps_per_workflow=10)
    facade = _RecordingFacade(
        recovered=Recovered(
            status="success",
            correlation_id="c",
            locator_spec=LocatorSpec(kind="xpath", value="//x"),
            strategy_id="rules",
        ),
        repo=repo,
    )
    await facade.recover_workflow_step(
        page=object(),
        app_id="a",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        workflow_context=_wf_context(),
    )
    updated = await facade.report_step_outcome(
        workflow_id="signup",
        step_id="fill_email",
        succeeded=True,
        note="action completed",
    )
    assert updated is True
    history = await repo.find_step_history("signup", "fill_email", limit=1)
    assert history[0].status == STEP_STATUS_STEP_SUCCEEDED
    assert history[0].note == "action completed"


@pytest.mark.asyncio
async def test_report_step_outcome_returns_false_when_no_repo() -> None:
    facade = _RecordingFacade(
        recovered=Recovered(status="success", correlation_id="c"),
        repo=None,
    )
    assert await facade.report_step_outcome(
        workflow_id="w", step_id="s", succeeded=True
    ) is False
