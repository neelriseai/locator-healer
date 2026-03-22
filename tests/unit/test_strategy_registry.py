import pytest

from xpath_healer.core.context import StrategyContext
from xpath_healer.core.models import BuildInput, Intent, LocatorSpec
from xpath_healer.core.strategy_registry import StrategyRegistry
from xpath_healer.core.strategies.base import Strategy


class _StrategyA(Strategy):
    id = "a"
    priority = 200
    stage = "rules"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        return True

    async def build(self, ctx: StrategyContext, inp: BuildInput) -> list[LocatorSpec]:
        return [LocatorSpec(kind="css", value="#a")]


class _StrategyB(Strategy):
    id = "b"
    priority = 100
    stage = "defaults"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        return True

    async def build(self, ctx: StrategyContext, inp: BuildInput) -> list[LocatorSpec]:
        return [LocatorSpec(kind="css", value="#b")]


@pytest.mark.asyncio
async def test_registry_orders_by_priority_and_filters_stage(simple_context: StrategyContext) -> None:
    registry = StrategyRegistry([_StrategyA(), _StrategyB()])
    inp = BuildInput(
        page=None,
        app_id="app",
        page_name="p",
        element_name="e",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={},
        intent=Intent(),
    )
    all_candidates = await registry.evaluate_all(simple_context, inp)
    assert [c.strategy_id for c in all_candidates] == ["b", "a"]

    rules_only = await registry.evaluate_all(simple_context, inp, allowed_stages={"rules"})
    assert [c.strategy_id for c in rules_only] == ["a"]
