"""Grid cell/header resolver by col-id and occurrence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from xpath_healer.core.models import BuildInput, LocatorSpec
from xpath_healer.core.strategies.base import Strategy, dedupe_locators
from xpath_healer.utils.text import normalize_text

if TYPE_CHECKING:
    from xpath_healer.core.context import StrategyContext


class GridCellByColIdStrategy(Strategy):
    id = "grid_cell_col_id"
    priority = 220
    stage = "defaults"

    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        field = normalize_text(field_type)
        has_col = bool(vars_map.get("col-id") or vars_map.get("col_id") or vars_map.get("column"))
        return field in {"gridcell", "grid_header", "gridheader", "columnheader"} and has_col

    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        col_id = inp.vars.get("col-id") or inp.vars.get("col_id") or inp.vars.get("column")
        if not col_id:
            return []
        occurrence = max(inp.intent.occurrence, 0)
        is_header = normalize_text(inp.field_type) in {"grid_header", "gridheader", "columnheader"}
        escaped = col_id.replace('"', '\\"')

        candidates = [
            LocatorSpec(
                kind="css",
                value=f'[col-id="{escaped}"]',
                options={"nth": occurrence} if occurrence else {},
            ),
            LocatorSpec(
                kind="xpath",
                value=(
                    f"//*[translate(@col-id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')="
                    f"'{col_id.casefold()}']"
                ),
                options={"nth": occurrence} if occurrence else {},
            ),
        ]

        if is_header:
            candidates.insert(
                0,
                LocatorSpec(
                    kind="css",
                    value=f'[role="columnheader"][col-id="{escaped}"]',
                    options={"nth": occurrence} if occurrence else {},
                ),
            )
        else:
            candidates.insert(
                0,
                LocatorSpec(
                    kind="css",
                    value=f'[role="gridcell"][col-id="{escaped}"]',
                    options={"nth": occurrence} if occurrence else {},
                ),
            )

        return dedupe_locators(candidates)

