"""Convenience facade for Appium callers.

Subclasses :class:`xpath_healer.api.base.BaseHealerFacade` and pre-wires
the :class:`AppiumPythonAdapter`. Mirrors the
``adapters/selenium_python/facade.py`` and
``adapters/playwright_python/facade.py`` pattern so all four backends
(Playwright, Selenium, Appium, custom) are switched the same way.
"""

from __future__ import annotations

from adapters.appium_python.adapter import AppiumPythonAdapter
from xpath_healer.api.base import BaseHealerFacade


class AppiumHealerFacade(BaseHealerFacade):
    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        kwargs.setdefault("adapter", AppiumPythonAdapter())
        super().__init__(*args, **kwargs)
