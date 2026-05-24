"""Appium adapter package — mobile-app automation backend.

Satisfies :class:`xpath_healer.core.automation.AutomationAdapter`, so
the entire healing pipeline (deterministic + memory + agent + RAG)
works for native iOS / Android targets with no per-stage changes.
"""

from adapters.appium_python.adapter import AppiumPythonAdapter, AppiumRuntimeLocator

__all__ = ["AppiumPythonAdapter", "AppiumRuntimeLocator"]
