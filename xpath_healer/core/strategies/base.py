"""Base strategy interface and helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict

from xpath_healer.core.models import BuildInput, LocatorSpec


class Strategy(ABC):
    id: str = "strategy"
    priority: int = 1000
    stage: str = "defaults"

    @abstractmethod
    def supports(self, field_type: str, vars_map: dict[str, str]) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def build(self, ctx: "StrategyContext", inp: BuildInput) -> list[LocatorSpec]:
        raise NotImplementedError


def safe_format(pattern: str, vars_map: dict[str, str]) -> str:
    return pattern.format_map(defaultdict(str, vars_map or {}))


def dedupe_locators(locators: list[LocatorSpec]) -> list[LocatorSpec]:
    seen: set[str] = set()
    out: list[LocatorSpec] = []
    for loc in locators:
        key = loc.stable_hash()
        if key in seen:
            continue
        seen.add(key)
        out.append(loc)
    return out

