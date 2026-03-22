"""Selenium Python healer facade."""

from __future__ import annotations

from xpath_healer.api.base import BaseHealerFacade

from adapters.selenium_python.adapter import SeleniumPythonAdapter


class SeleniumHealerFacade(BaseHealerFacade):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("adapter", SeleniumPythonAdapter())
        super().__init__(*args, **kwargs)
