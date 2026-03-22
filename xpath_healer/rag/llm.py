"""LLM adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLM(ABC):
    @abstractmethod
    async def suggest_locators(self, prompt_payload: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

