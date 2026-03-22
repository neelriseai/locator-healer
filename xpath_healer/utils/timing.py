"""Timing helpers."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass(slots=True)
class Timing:
    start: float
    end: float | None = None

    @property
    def elapsed_ms(self) -> float:
        end = self.end if self.end is not None else time.perf_counter()
        return (end - self.start) * 1000.0


@contextmanager
def timed() -> Iterator[Timing]:
    span = Timing(start=time.perf_counter())
    try:
        yield span
    finally:
        span.end = time.perf_counter()

