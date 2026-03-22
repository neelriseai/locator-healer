"""Builder facade around strategy registry."""

from __future__ import annotations

from xpath_healer.core.models import BuildInput, CandidateSpec
from xpath_healer.core.strategy_registry import StrategyRegistry


class XPathBuilder:
    def __init__(self, registry: StrategyRegistry) -> None:
        self.registry = registry

    async def build_all_candidates(
        self,
        ctx: "StrategyContext",
        inp: BuildInput,
        allowed_stages: set[str] | None = None,
    ) -> list[CandidateSpec]:
        return await self.registry.evaluate_all(ctx, inp, allowed_stages=allowed_stages)

