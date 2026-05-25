"""PostgreSQL backend for workflow run history.

Same protocol as :class:`InMemoryWorkflowRunRepository` /
:class:`JsonWorkflowRunRepository` — drop-in. Schema is intentionally
minimal: one table, indexed by ``(workflow_id, step_id, recorded_at)``
for the only query shape the healer issues.

Concurrency: row-level INSERTs are serialised by Postgres; the per-
workflow retention prune runs in a single transaction so two writers
can't double-evict. No process-level lock required.
"""

from __future__ import annotations

import json
import logging
from typing import Any

try:
    import asyncpg  # type: ignore
except Exception:  # pragma: no cover - optional dep
    asyncpg = None  # type: ignore[assignment]

from xpath_healer.core.workflow import (
    STEP_STATUS_HEAL_FAILED,
    STEP_STATUS_HEAL_SUCCEEDED,
    StepRun,
    WorkflowRun,
)
from xpath_healer.store.workflow_run_repository import WorkflowRunRepository


_HEAL_STATUSES = {STEP_STATUS_HEAL_SUCCEEDED, STEP_STATUS_HEAL_FAILED}


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS xh_workflow_step_runs (
    id               BIGSERIAL PRIMARY KEY,
    workflow_id      TEXT     NOT NULL,
    step_id          TEXT     NOT NULL,
    status           TEXT     NOT NULL,
    locator_used     JSONB    NOT NULL DEFAULT '{}'::JSONB,
    healer_stage     TEXT     NOT NULL DEFAULT '',
    page_signature   TEXT     NOT NULL DEFAULT '',
    duration_ms      DOUBLE PRECISION,
    failure_reason   TEXT     NOT NULL DEFAULT '',
    note             TEXT     NOT NULL DEFAULT '',
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS xh_wf_step_runs_lookup_idx
    ON xh_workflow_step_runs (workflow_id, step_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS xh_wf_step_runs_wf_idx
    ON xh_workflow_step_runs (workflow_id, recorded_at DESC);
"""


class PostgresWorkflowRunRepository(WorkflowRunRepository):
    def __init__(
        self,
        dsn: str,
        *,
        pool_min_size: int = 1,
        pool_max_size: int = 5,
        auto_init_schema: bool = False,
        max_steps_per_workflow: int = 50,
    ) -> None:
        if max_steps_per_workflow < 1:
            raise ValueError("max_steps_per_workflow must be >= 1")
        self.dsn = dsn
        self.pool_min_size = max(1, int(pool_min_size))
        self.pool_max_size = max(self.pool_min_size, int(pool_max_size))
        self.auto_init_schema = bool(auto_init_schema)
        self._max = max_steps_per_workflow
        self._pool: Any = None
        self.logger = logging.getLogger("xpath_healer.store.workflow_run_pg")

    async def connect(self) -> None:
        if self._pool is not None:
            return
        if asyncpg is None:
            raise RuntimeError(
                "asyncpg is not installed. Install with: python -m pip install asyncpg"
            )
        self._pool = await asyncpg.create_pool(  # type: ignore[union-attr]
            dsn=self.dsn,
            min_size=self.pool_min_size,
            max_size=self.pool_max_size,
            command_timeout=15,
        )
        if self.auto_init_schema:
            await self.init_schema()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def init_schema(self) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(_SCHEMA_SQL)

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            await self.connect()
        return self._pool

    @staticmethod
    def schema_sql() -> str:
        return _SCHEMA_SQL

    # ------------------------------------------------------------------
    # WorkflowRunRepository implementation
    # ------------------------------------------------------------------

    async def record_step(self, step_run: StepRun) -> None:
        pool = await self._ensure_pool()
        locator_json = json.dumps(step_run.locator_used or {}, separators=(",", ":"))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO xh_workflow_step_runs
                      (workflow_id, step_id, status, locator_used, healer_stage,
                       page_signature, duration_ms, failure_reason, note, recorded_at)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10)
                    """,
                    step_run.workflow_id,
                    step_run.step_id,
                    step_run.status,
                    locator_json,
                    step_run.healer_stage,
                    step_run.page_signature_hash,
                    step_run.duration_ms,
                    step_run.failure_reason,
                    step_run.note,
                    step_run.recorded_at,
                )
                # Retention prune — keep newest ``self._max`` rows per workflow.
                await conn.execute(
                    """
                    DELETE FROM xh_workflow_step_runs
                    WHERE workflow_id = $1
                      AND id IN (
                          SELECT id FROM xh_workflow_step_runs
                          WHERE workflow_id = $1
                          ORDER BY recorded_at ASC
                          OFFSET $2
                      )
                    """,
                    step_run.workflow_id,
                    self._max,
                )

    async def update_step_status(
        self,
        workflow_id: str,
        step_id: str,
        new_status: str,
        *,
        note: str = "",
    ) -> bool:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id FROM xh_workflow_step_runs
                WHERE workflow_id = $1
                  AND step_id = $2
                  AND status = ANY($3::text[])
                ORDER BY recorded_at DESC
                LIMIT 1
                """,
                workflow_id,
                step_id,
                list(_HEAL_STATUSES),
            )
            if row is None:
                return False
            await conn.execute(
                """
                UPDATE xh_workflow_step_runs
                SET status = $2,
                    note = CASE WHEN $3 = '' THEN note ELSE $3 END
                WHERE id = $1
                """,
                row["id"],
                new_status,
                note,
            )
            return True

    async def get_run(self, workflow_id: str) -> WorkflowRun | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT workflow_id, step_id, status, locator_used, healer_stage,
                       page_signature, duration_ms, failure_reason, note, recorded_at
                FROM xh_workflow_step_runs
                WHERE workflow_id = $1
                ORDER BY recorded_at ASC
                """,
                workflow_id,
            )
        if not rows:
            return None
        steps = [self._row_to_step_run(row) for row in rows]
        return WorkflowRun(workflow_id=workflow_id, steps=steps)

    async def find_step_history(
        self,
        workflow_id: str,
        step_id: str,
        *,
        limit: int = 10,
    ) -> list[StepRun]:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT workflow_id, step_id, status, locator_used, healer_stage,
                       page_signature, duration_ms, failure_reason, note, recorded_at
                FROM xh_workflow_step_runs
                WHERE workflow_id = $1
                  AND step_id = $2
                ORDER BY recorded_at DESC
                LIMIT $3
                """,
                workflow_id,
                step_id,
                max(0, int(limit)),
            )
        return [self._row_to_step_run(row) for row in rows]

    @staticmethod
    def _row_to_step_run(row: Any) -> StepRun:
        locator_raw = row["locator_used"]
        if isinstance(locator_raw, str):
            try:
                locator = json.loads(locator_raw)
            except Exception:
                locator = {}
        elif isinstance(locator_raw, dict):
            locator = dict(locator_raw)
        else:
            locator = {}
        return StepRun(
            workflow_id=str(row["workflow_id"] or ""),
            step_id=str(row["step_id"] or ""),
            status=str(row["status"] or ""),
            locator_used=locator,
            healer_stage=str(row["healer_stage"] or ""),
            page_signature_hash=str(row["page_signature"] or ""),
            duration_ms=row["duration_ms"],
            failure_reason=str(row["failure_reason"] or ""),
            note=str(row["note"] or ""),
            recorded_at=row["recorded_at"],
        )
