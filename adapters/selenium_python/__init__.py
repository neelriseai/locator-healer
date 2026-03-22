"""Selenium Python adapter exports."""

__all__ = ["SeleniumHealerFacade", "SeleniumPythonAdapter"]


def __getattr__(name: str):
    if name == "SeleniumPythonAdapter":
        from adapters.selenium_python.adapter import SeleniumPythonAdapter

        return SeleniumPythonAdapter
    if name == "SeleniumHealerFacade":
        from adapters.selenium_python.facade import SeleniumHealerFacade

        return SeleniumHealerFacade
    raise AttributeError(name)
