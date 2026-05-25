"""Telemetry — measurable evidence for the product-philosophy claims.

We claim "cost-efficient" and "high performance" but had no numbers
behind those claims. This module provides:

  * :class:`TelemetryCounter` — a thread-safe-ish counter that the
    orchestrator increments. Lives for the duration of one workflow
    run and ends up in ``OrchestrationResult.metadata["telemetry"]``.
  * :class:`TelemetryLLMClient` — a transparent wrapper around any
    ``LLMClient`` that counts chat invocations, tokens (prompt /
    completion / total), and elapsed wall time.
  * :class:`TelemetryVisualInspector` — same idea for vision calls.

All wrappers are zero-cost when the counter is ``None`` — they
forward straight to the underlying client.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from xpath_healer.llm.client import (
    ChatMessage,
    ChatResponse,
    LLMClient,
    ToolDefinition,
)


@dataclass(slots=True)
class SLO:
    """Service-level objectives for a workflow run.

    Numbers come from the cost / performance targets we want to commit
    to. Keep them concrete so we can detect regressions, not vibes.

    Defaults are calibrated to "an n-step browsing-and-extract workflow
    with one decomposer + one verifier LLM call per page". A run with
    persistent failures + many retries will exceed these; that should
    visibly fail the SLO instead of silently degrading.
    """

    # Total wall time per workflow run, measured in seconds. Real
    # e-commerce phase-1 runs hit ~200s on slow networks (Flipkart's
    # heavy JS, anti-bot delays). Per-product drills typically <15s.
    max_total_seconds: float = 240.0
    # Per-step wall time before we flag a slow step. Tuned for the
    # known slow case (extract_auto_discover on Flipkart's lazy-loaded
    # results grid can take 100s+ from cold cache).
    max_step_ms: float = 240_000.0
    # Cost ceiling per workflow run.
    max_llm_tokens: int = 60_000
    # Cap the LLM call count — each call is at least one decomposer or
    # verifier or extract; >20 means we have an unrecovered cascade.
    max_llm_calls: int = 20
    # Vision is more expensive per token (image input); cap separately.
    max_vision_calls: int = 8

    def check(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        """Compare telemetry to the SLO. Returns a report dict with
        per-target ``ok`` / ``observed`` / ``limit``. Never raises."""
        if not telemetry:
            return {"ok": False, "error": "no telemetry"}
        checks: dict[str, dict[str, Any]] = {}
        def _add(name: str, observed: float, limit: float, *, lower_is_better: bool = True) -> None:
            ok = (observed <= limit) if lower_is_better else (observed >= limit)
            checks[name] = {"ok": bool(ok), "observed": observed, "limit": limit}
        _add("total_seconds", float(telemetry.get("total_seconds") or 0.0), self.max_total_seconds)
        _add("llm_calls", int(telemetry.get("llm_calls") or 0), self.max_llm_calls)
        _add("llm_total_tokens", int(telemetry.get("llm_total_tokens") or 0), self.max_llm_tokens)
        _add("vision_calls", int(telemetry.get("vision_calls") or 0), self.max_vision_calls)
        slow_steps = {
            sid: ms for sid, ms in (telemetry.get("step_durations_ms") or {}).items()
            if float(ms) > self.max_step_ms
        }
        checks["max_step_ms"] = {
            "ok": not slow_steps,
            "slow_steps": slow_steps,
            "limit": self.max_step_ms,
        }
        all_ok = all(c.get("ok") for c in checks.values())
        return {"ok": all_ok, "checks": checks}


@dataclass(slots=True)
class TelemetryCounter:
    """Per-workflow-run counters. Pure data; no locking needed because
    the orchestrator runs steps sequentially within a single asyncio
    task."""

    llm_calls: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    llm_total_tokens: int = 0
    llm_seconds: float = 0.0

    vision_calls: int = 0
    vision_seconds: float = 0.0

    # Heal-strategy distribution: which strategy actually healed each
    # successfully-located step (e.g. {"rules": 3, "page_index.rank": 2,
    # "visual_candidate_pick": 1}). Excludes failed heals.
    heal_strategy_counts: dict[str, int] = field(default_factory=dict)

    # Per-step durations (ms) keyed by step_id for percentile work.
    step_durations_ms: dict[str, float] = field(default_factory=dict)

    # The orchestrator's wall time for the whole run (set by runner).
    total_seconds: float = 0.0

    def add_heal_strategy(self, strategy: str) -> None:
        if not strategy:
            return
        self.heal_strategy_counts[strategy] = self.heal_strategy_counts.get(strategy, 0) + 1

    def reset(self) -> None:
        """Zero every counter. Used between workflow runs so each
        run's telemetry / SLO check reflects only its own work."""
        self.llm_calls = 0
        self.llm_prompt_tokens = 0
        self.llm_completion_tokens = 0
        self.llm_total_tokens = 0
        self.llm_seconds = 0.0
        self.vision_calls = 0
        self.vision_seconds = 0.0
        self.heal_strategy_counts = {}
        self.step_durations_ms = {}
        self.total_seconds = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "llm_calls": self.llm_calls,
            "llm_prompt_tokens": self.llm_prompt_tokens,
            "llm_completion_tokens": self.llm_completion_tokens,
            "llm_total_tokens": self.llm_total_tokens,
            "llm_seconds": round(self.llm_seconds, 3),
            "vision_calls": self.vision_calls,
            "vision_seconds": round(self.vision_seconds, 3),
            "heal_strategy_counts": dict(self.heal_strategy_counts),
            "step_durations_ms": {k: round(v, 1) for k, v in self.step_durations_ms.items()},
            # Total seconds keeps microsecond precision so tiny (mocked)
            # runs still report a non-zero duration; consumers can format
            # it however they like.
            "total_seconds": round(self.total_seconds, 6),
        }


class TelemetryLLMClient(LLMClient):
    """Wrap any ``LLMClient`` to count calls + tokens + duration.

    Forwards every kwarg unchanged. The wrapper itself adds no token
    overhead — it only measures what the inner client already returns
    in :attr:`ChatResponse.metadata.usage`.
    """

    def __init__(self, inner: LLMClient, counter: TelemetryCounter) -> None:
        self.inner = inner
        self.counter = counter

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        t0 = time.perf_counter()
        try:
            return await self._call_and_count(
                messages, tools=tools, temperature=temperature, max_tokens=max_tokens
            )
        finally:
            self.counter.llm_seconds += time.perf_counter() - t0

    async def _call_and_count(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> ChatResponse:
        response = await self.inner.chat(
            messages, tools=tools, temperature=temperature, max_tokens=max_tokens
        )
        self.counter.llm_calls += 1
        usage = (response.metadata or {}).get("usage") or {}
        self.counter.llm_prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.counter.llm_completion_tokens += int(usage.get("completion_tokens") or 0)
        self.counter.llm_total_tokens += int(usage.get("total_tokens") or 0)
        return response


class TelemetryVisualInspector:
    """Wrap a ``VisualInspector`` to count vision calls + duration.

    Vision calls are separately tracked from chat calls because they
    cost more per token (image input) and we want a clean ratio for
    "how often does vision fire vs. how often is the workflow run"
    in the product-philosophy claims.
    """

    def __init__(self, inner: Any, counter: TelemetryCounter) -> None:
        self.inner = inner
        self.counter = counter

    async def inspect(self, **kwargs):
        t0 = time.perf_counter()
        try:
            res = await self.inner.inspect(**kwargs)
            return res
        finally:
            self.counter.vision_calls += 1
            self.counter.vision_seconds += time.perf_counter() - t0

    async def pick_candidate(self, **kwargs):
        t0 = time.perf_counter()
        try:
            res = await self.inner.pick_candidate(**kwargs)
            return res
        finally:
            self.counter.vision_calls += 1
            self.counter.vision_seconds += time.perf_counter() - t0
