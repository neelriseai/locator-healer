"""Playwright Python healer facade."""

from __future__ import annotations

from xpath_healer.api.base import BaseHealerFacade

from adapters.playwright_python.adapter import PlaywrightPythonAdapter


class PlaywrightHealerFacade(BaseHealerFacade):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("adapter", PlaywrightPythonAdapter())
        super().__init__(*args, **kwargs)
