"""Automation framework adapter contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

if False:  # pragma: no cover
    from xpath_healer.core.models import LocatorSpec


@runtime_checkable
class RuntimeLocator(Protocol):
    raw: Any

    async def count(self) -> int: ...

    def nth(self, index: int) -> "RuntimeLocator": ...

    async def is_visible(self) -> bool: ...

    async def is_enabled(self) -> bool: ...

    async def evaluate(self, script: str, arg: Any = None) -> Any: ...

    async def bounding_box(self) -> dict[str, float] | None: ...


class AutomationAdapter(ABC):
    """Adapter bridge for framework-specific locator and DOM operations."""

    name: str

    @abstractmethod
    async def resolve_locator(self, root: Any, locator_spec: "LocatorSpec") -> RuntimeLocator:
        raise NotImplementedError

    @abstractmethod
    async def capture_page_html(self, page: Any) -> str:
        raise NotImplementedError
