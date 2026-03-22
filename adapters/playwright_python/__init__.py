"""Playwright Python adapter exports."""

__all__ = ["PlaywrightHealerFacade", "PlaywrightPythonAdapter"]


def __getattr__(name: str):
    if name == "PlaywrightPythonAdapter":
        from adapters.playwright_python.adapter import PlaywrightPythonAdapter

        return PlaywrightPythonAdapter
    if name == "PlaywrightHealerFacade":
        from adapters.playwright_python.facade import PlaywrightHealerFacade

        return PlaywrightHealerFacade
    raise AttributeError(name)
