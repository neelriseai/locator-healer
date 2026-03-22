"""Retriever adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Retriever(ABC):
    @abstractmethod
    async def retrieve(self, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        raise NotImplementedError

