"""Factory helpers for configurable adapter selection."""

from __future__ import annotations

from typing import Any

from adapters.playwright_python.adapter import PlaywrightPythonAdapter
from adapters.playwright_python.facade import PlaywrightHealerFacade
from adapters.selenium_python.adapter import SeleniumPythonAdapter
from adapters.selenium_python.facade import SeleniumHealerFacade
from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.config import HealerConfig


def create_adapter(name: str | None = None) -> AutomationAdapter:
    adapter_name = (name or "playwright_python").strip().casefold()
    if adapter_name == "playwright_python":
        return PlaywrightPythonAdapter()
    if adapter_name == "selenium_python":
        return SeleniumPythonAdapter()
    raise ValueError(f"Unsupported adapter: {name}")


def create_healer_facade(
    adapter_name: str | None = None,
    config: HealerConfig | None = None,
    **kwargs: Any,
) -> Any:
    effective_config = config or HealerConfig.from_env()
    resolved_name = (adapter_name or effective_config.adapter.name or "playwright_python").strip().casefold()
    effective_config.adapter.name = resolved_name
    if resolved_name == "selenium_python":
        return SeleniumHealerFacade(config=effective_config, **kwargs)
    if resolved_name == "playwright_python":
        return PlaywrightHealerFacade(config=effective_config, **kwargs)
    raise ValueError(f"Unsupported adapter: {resolved_name}")
