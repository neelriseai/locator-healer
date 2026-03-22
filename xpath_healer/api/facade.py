"""Backward-compatible Playwright facade export."""

from adapters.playwright_python.facade import PlaywrightHealerFacade


class XPathHealerFacade(PlaywrightHealerFacade):
    """Compatibility facade that keeps Playwright as the default adapter."""
