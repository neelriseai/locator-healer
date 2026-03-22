"""Public API entry points."""

__all__ = ["BaseHealerFacade", "XPathHealerFacade", "create_adapter", "create_healer_facade"]


def __getattr__(name: str):
    if name == "BaseHealerFacade":
        from xpath_healer.api.base import BaseHealerFacade

        return BaseHealerFacade
    if name == "XPathHealerFacade":
        from xpath_healer.api.facade import XPathHealerFacade

        return XPathHealerFacade
    if name == "create_adapter":
        from xpath_healer.api.factory import create_adapter

        return create_adapter
    if name == "create_healer_facade":
        from xpath_healer.api.factory import create_healer_facade

        return create_healer_facade
    raise AttributeError(name)
