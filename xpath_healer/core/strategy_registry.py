"""Ordered strategy registry and candidate evaluation helpers."""

from __future__ import annotations

from typing import Iterable

from xpath_healer.core.models import BuildInput, CandidateSpec
from xpath_healer.core.strategies.base import Strategy


class StrategyRegistry:
    def __init__(self, strategies: Iterable[Strategy] | None = None) -> None:
        self._strategies: list[Strategy] = []
        if strategies:
            for strategy in strategies:
                self.register(strategy)

    def register(self, strategy: Strategy) -> None:
        self._strategies.append(strategy)
        self._strategies.sort(key=lambda s: s.priority)

    def ordered(self) -> list[Strategy]:
        return list(self._strategies)

    async def evaluate_all(
        self,
        ctx: "StrategyContext",
        inp: BuildInput,
        allowed_stages: set[str] | None = None,
    ) -> list[CandidateSpec]:
        candidates: list[CandidateSpec] = []
        seen: set[str] = set()

        for strategy in self._strategies:
            if allowed_stages and strategy.stage not in allowed_stages:
                continue
            if not strategy.supports(inp.field_type, inp.vars):
                continue
            built = await strategy.build(ctx, inp)
            for locator in built:
                key = f"{strategy.id}:{locator.stable_hash()}"
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(CandidateSpec(strategy_id=strategy.id, locator=locator, stage=strategy.stage))
        return candidates

