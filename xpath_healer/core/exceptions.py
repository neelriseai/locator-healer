"""Exceptions for healing lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

from xpath_healer.core.models import StrategyTrace


class XPathHealerError(Exception):
    """Base exception for healer failures."""


@dataclass(slots=True)
class RecoveryFailed(XPathHealerError):
    message: str
    correlation_id: str
    trace: list[StrategyTrace]

    def __str__(self) -> str:
        return f"{self.message} (correlation_id={self.correlation_id})"

