"""Embedding adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Embedder(ABC):
    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

