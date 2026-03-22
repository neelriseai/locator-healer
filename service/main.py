"""Thin FastAPI wrapper around library-first XPath healer."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from xpath_healer.api import create_healer_facade
from xpath_healer.core.models import HealingHints, LocatorSpec
from service.session_registry import AutomationSessionRegistry, resolve_session


class LocatorSpecModel(BaseModel):
    kind: str
    value: str
    options: dict[str, Any] = Field(default_factory=dict)
    scope: "LocatorSpecModel | None" = None

    def to_domain(self) -> LocatorSpec:
        return LocatorSpec(
            kind=self.kind,
            value=self.value,
            options=self.options,
            scope=self.scope.to_domain() if self.scope else None,
        )

    @classmethod
    def from_domain(cls, locator: LocatorSpec) -> "LocatorSpecModel":
        return cls(
            kind=locator.kind,
            value=locator.value,
            options=locator.options,
            scope=cls.from_domain(locator.scope) if locator.scope else None,
        )


LocatorSpecModel.model_rebuild()


class HealRequest(BaseModel):
    app_id: str = "default"
    page_name: str
    element_name: str
    field_type: str
    fallback: LocatorSpecModel
    vars: dict[str, str] = Field(default_factory=dict)
    hints: dict[str, Any] | None = None
    session_id: str | None = None


class GenerateRequest(BaseModel):
    page_name: str
    element_name: str
    field_type: str
    vars: dict[str, str] = Field(default_factory=dict)
    hints: dict[str, Any] | None = None


def create_app(
    facade: Any | None = None,
    page_resolver: Callable[[str], Awaitable[Any] | Any] | None = None,
    session_registry: AutomationSessionRegistry | None = None,
) -> FastAPI:
    app = FastAPI(title="XPath Healer Service", version="0.1.0")
    healer = facade or create_healer_facade()
    registry = session_registry or AutomationSessionRegistry()
    app.state.session_registry = registry

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/generate")
    async def generate(req: GenerateRequest) -> dict[str, Any]:
        hints = HealingHints.from_dict(req.hints) if req.hints else None
        locator = await healer.generate_locator_async(
            page_name=req.page_name,
            element_name=req.element_name,
            field_type=req.field_type,
            vars=req.vars,
            hints=hints,
        )
        return {"locator_spec": LocatorSpecModel.from_domain(locator).model_dump()}

    @app.post("/heal")
    async def heal(req: HealRequest) -> dict[str, Any]:
        if not req.session_id:
            raise HTTPException(status_code=400, detail="session_id is required for /heal.")

        page = await resolve_session(req.session_id, resolver=page_resolver, registry=registry)
        if page is None:
            raise HTTPException(status_code=404, detail=f"No page found for session_id={req.session_id}")

        hints = HealingHints.from_dict(req.hints) if req.hints else None
        recovered = await healer.recover_locator(
            page=page,
            app_id=req.app_id,
            page_name=req.page_name,
            element_name=req.element_name,
            field_type=req.field_type,
            fallback=req.fallback.to_domain(),
            vars=req.vars,
            hints=hints,
        )
        payload: dict[str, Any] = {
            "status": recovered.status,
            "correlation_id": recovered.correlation_id,
            "strategy_id": recovered.strategy_id,
            "trace": [entry.to_dict() for entry in recovered.trace],
            "error": recovered.error,
        }
        if recovered.locator_spec:
            payload["locator_spec"] = LocatorSpecModel.from_domain(recovered.locator_spec).model_dump()
        if recovered.metadata:
            payload["updated_meta"] = recovered.metadata.to_dict()
        return payload

    return app


app = create_app()
