"""Persistence for workflow-run history (Phase 4b).

Two impls ship with the package:

* :class:`InMemoryWorkflowRunRepository` — for tests and for callers
  that don't need cross-process persistence.
* :class:`JsonWorkflowRunRepository` — atomic-write JSON file per
  workflow_id under a configured directory. Survives restarts so the
  Phase 4c replay cache has data on cold start.

Both implementations enforce ``max_steps_per_workflow`` retention: when
appending a new step would exceed the cap, the oldest entries are
evicted. Keeps storage flat regardless of how long the system runs.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from xpath_healer.core.workflow import (
    STEP_STATUS_HEAL_FAILED,
    STEP_STATUS_HEAL_SUCCEEDED,
    STEP_STATUS_STEP_FAILED,
    STEP_STATUS_STEP_SUCCEEDED,
    StepRun,
    WorkflowRun,
)


_HEAL_STATUSES = {STEP_STATUS_HEAL_SUCCEEDED, STEP_STATUS_HEAL_FAILED}
_FINAL_STATUSES = {STEP_STATUS_STEP_SUCCEEDED, STEP_STATUS_STEP_FAILED}


@runtime_checkable
class WorkflowRunRepository(Protocol):
    """Async append-log of step outcomes per workflow."""

    async def record_step(self, step_run: StepRun) -> None:
        ...

    async def update_step_status(
        self,
        workflow_id: str,
        step_id: str,
        new_status: str,
        *,
        note: str = "",
    ) -> bool:
        """Upgrade most recent matching record's status.

        Returns ``True`` if a record was found and updated, ``False``
        otherwise.
        """
        ...

    async def get_run(self, workflow_id: str) -> WorkflowRun | None:
        ...

    async def find_step_history(
        self,
        workflow_id: str,
        step_id: str,
        *,
        limit: int = 10,
    ) -> list[StepRun]:
        """Most-recent-first slice of matching step records."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class InMemoryWorkflowRunRepository(WorkflowRunRepository):
    """Pure-dict implementation suitable for tests and ephemeral CI."""

    def __init__(self, *, max_steps_per_workflow: int = 50) -> None:
        if max_steps_per_workflow < 1:
            raise ValueError("max_steps_per_workflow must be >= 1")
        self._max = max_steps_per_workflow
        self._runs: dict[str, WorkflowRun] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, workflow_id: str) -> asyncio.Lock:
        lock = self._locks.get(workflow_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[workflow_id] = lock
        return lock

    async def record_step(self, step_run: StepRun) -> None:
        wid = step_run.workflow_id
        async with self._lock_for(wid):
            run = self._runs.get(wid)
            if run is None:
                run = WorkflowRun(workflow_id=wid)
                self._runs[wid] = run
            run.steps.append(step_run)
            # Evict oldest if over cap.
            overflow = len(run.steps) - self._max
            if overflow > 0:
                del run.steps[:overflow]

    async def update_step_status(
        self,
        workflow_id: str,
        step_id: str,
        new_status: str,
        *,
        note: str = "",
    ) -> bool:
        async with self._lock_for(workflow_id):
            run = self._runs.get(workflow_id)
            if run is None:
                return False
            # Most recent matching heal_* record gets upgraded.
            for step in reversed(run.steps):
                if step.step_id != step_id:
                    continue
                if step.status not in _HEAL_STATUSES:
                    continue
                step.status = new_status
                if note:
                    step.note = note
                return True
            return False

    async def get_run(self, workflow_id: str) -> WorkflowRun | None:
        run = self._runs.get(workflow_id)
        if run is None:
            return None
        # Defensive copy so callers can mutate without surprise.
        return WorkflowRun(
            workflow_id=run.workflow_id,
            steps=[StepRun.from_dict(s.to_dict()) for s in run.steps],
            metadata=dict(run.metadata),
        )

    async def find_step_history(
        self,
        workflow_id: str,
        step_id: str,
        *,
        limit: int = 10,
    ) -> list[StepRun]:
        run = self._runs.get(workflow_id)
        if run is None:
            return []
        matches = [s for s in run.steps if s.step_id == step_id]
        matches.reverse()  # most recent first
        return [StepRun.from_dict(s.to_dict()) for s in matches[: max(0, limit)]]


# ---------------------------------------------------------------------------
# JSON-file implementation
# ---------------------------------------------------------------------------


class JsonWorkflowRunRepository(WorkflowRunRepository):
    """One JSON file per workflow under ``base_dir``.

    Atomic writes via temp-file + ``os.replace`` so a crash between
    write and rename leaves either the old file or the new one — never
    a half-written one.
    """

    def __init__(self, base_dir: str | Path, *, max_steps_per_workflow: int = 50) -> None:
        if max_steps_per_workflow < 1:
            raise ValueError("max_steps_per_workflow must be >= 1")
        self._base = Path(base_dir)
        self._max = max_steps_per_workflow
        self._locks: dict[str, asyncio.Lock] = {}
        self._base.mkdir(parents=True, exist_ok=True)

    def _lock_for(self, workflow_id: str) -> asyncio.Lock:
        lock = self._locks.get(workflow_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[workflow_id] = lock
        return lock

    def _path_for(self, workflow_id: str) -> Path:
        # Slugify the id so callers can't path-traverse through us.
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in workflow_id)
        if not safe:
            safe = "unnamed"
        return self._base / f"{safe}.json"

    async def _read(self, workflow_id: str) -> WorkflowRun:
        path = self._path_for(workflow_id)
        if not path.exists():
            return WorkflowRun(workflow_id=workflow_id)
        try:
            text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            payload = json.loads(text)
        except Exception:
            # Corrupt file — start fresh rather than blocking the caller.
            return WorkflowRun(workflow_id=workflow_id)
        return WorkflowRun.from_dict(payload)

    async def _write(self, run: WorkflowRun) -> None:
        path = self._path_for(run.workflow_id)
        tmp = path.with_suffix(path.suffix + ".tmp")
        text = json.dumps(run.to_dict(), ensure_ascii=True, separators=(",", ":"))

        def _do_write() -> None:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)

        await asyncio.to_thread(_do_write)

    async def record_step(self, step_run: StepRun) -> None:
        async with self._lock_for(step_run.workflow_id):
            run = await self._read(step_run.workflow_id)
            run.steps.append(step_run)
            overflow = len(run.steps) - self._max
            if overflow > 0:
                del run.steps[:overflow]
            await self._write(run)

    async def update_step_status(
        self,
        workflow_id: str,
        step_id: str,
        new_status: str,
        *,
        note: str = "",
    ) -> bool:
        async with self._lock_for(workflow_id):
            run = await self._read(workflow_id)
            for step in reversed(run.steps):
                if step.step_id != step_id:
                    continue
                if step.status not in _HEAL_STATUSES:
                    continue
                step.status = new_status
                if note:
                    step.note = note
                await self._write(run)
                return True
            return False

    async def get_run(self, workflow_id: str) -> WorkflowRun | None:
        run = await self._read(workflow_id)
        if not run.steps:
            # No history yet — return None to mirror the in-memory repo.
            return None
        return run

    async def find_step_history(
        self,
        workflow_id: str,
        step_id: str,
        *,
        limit: int = 10,
    ) -> list[StepRun]:
        run = await self._read(workflow_id)
        matches = [s for s in run.steps if s.step_id == step_id]
        matches.reverse()
        return matches[: max(0, limit)]


# Convenience for stage code that wants to be defensive when the repo
# isn't configured.
async def safe_record_step(
    repo: WorkflowRunRepository | None,
    step_run: StepRun,
) -> None:
    if repo is None:
        return
    with contextlib.suppress(Exception):
        await repo.record_step(step_run)


async def safe_update_step_status(
    repo: WorkflowRunRepository | None,
    workflow_id: str,
    step_id: str,
    new_status: str,
    *,
    note: str = "",
) -> bool:
    if repo is None:
        return False
    try:
        return await repo.update_step_status(workflow_id, step_id, new_status, note=note)
    except Exception:
        return False


__all__ = [
    "InMemoryWorkflowRunRepository",
    "JsonWorkflowRunRepository",
    "WorkflowRunRepository",
    "safe_record_step",
    "safe_update_step_status",
]
