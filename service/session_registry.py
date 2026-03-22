"""In-memory automation session registry for service mode."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any


class AutomationSessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}

    def register(self, session_id: str, session: Any) -> None:
        self._sessions[str(session_id)] = session

    def get(self, session_id: str) -> Any | None:
        return self._sessions.get(str(session_id))

    def remove(self, session_id: str) -> Any | None:
        return self._sessions.pop(str(session_id), None)

    async def resolve(self, session_id: str) -> Any | None:
        return self.get(session_id)


async def resolve_session(
    session_id: str,
    resolver: Callable[[str], Awaitable[Any] | Any] | None = None,
    registry: AutomationSessionRegistry | None = None,
) -> Any | None:
    if resolver is not None:
        value = resolver(session_id)
        if inspect.isawaitable(value):
            return await value
        return value
    if registry is not None:
        return await registry.resolve(session_id)
    return None
