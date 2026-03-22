import logging

import pytest

from adapters.playwright_python.adapter import PlaywrightPythonAdapter
from xpath_healer.core.builder import XPathBuilder
from xpath_healer.core.config import HealerConfig
from xpath_healer.core.context import StrategyContext
from xpath_healer.core.healing_service import HealingService
from xpath_healer.core.models import BuildInput, ElementMeta, ElementSignature, Intent, LocatorSpec
from xpath_healer.core.page_index import PageIndexer
from xpath_healer.core.strategy_registry import StrategyRegistry
from xpath_healer.store.memory_repository import InMemoryMetadataRepository


@pytest.mark.asyncio
async def test_fingerprint_stage_builds_candidates_from_structural_match() -> None:
    repository = InMemoryMetadataRepository()
    neighbor = ElementMeta(
        app_id="app",
        page_name="login",
        element_name="email_neighbor",
        field_type="textbox",
        last_good_locator=LocatorSpec(kind="css", value='[name="email"]'),
        signature=ElementSignature(
            tag="input",
            stable_attrs={"type": "text", "role": "textbox", "name": "email"},
            short_text="Email",
            container_path=["role:form", "testid:login-card"],
        ),
        locator_variants={"robust_xpath": LocatorSpec(kind="xpath", value='//*[@name="email"]')},
    )
    await repository.upsert(neighbor)

    current_meta = ElementMeta(
        app_id="app",
        page_name="login",
        element_name="email",
        field_type="textbox",
        signature=ElementSignature(
            tag="input",
            stable_attrs={"type": "text", "role": "textbox"},
            short_text="Email",
            container_path=["role:form", "testid:login-card"],
        ),
    )
    service = HealingService(builder=XPathBuilder(StrategyRegistry([])))
    adapter = PlaywrightPythonAdapter()
    ctx = StrategyContext(
        config=HealerConfig(),
        adapter=adapter,
        repository=repository,
        validator=None,  # type: ignore[arg-type]
        similarity=None,  # type: ignore[arg-type]
        signature_extractor=None,  # type: ignore[arg-type]
        dom_snapshotter=None,  # type: ignore[arg-type]
        dom_miner=None,  # type: ignore[arg-type]
        page_indexer=PageIndexer(),
        logger=logging.getLogger("test"),
    )
    inp = BuildInput(
        page=None,
        app_id="app",
        page_name="login",
        element_name="email",
        field_type="textbox",
        fallback=LocatorSpec(kind="xpath", value="//missing"),
        vars={"label": "Email"},
        intent=Intent.from_vars({"label": "Email", "text": "Email"}),
    )

    out = await service._fingerprint_candidates(ctx, inp, current_meta)

    assert out
    assert out[0].stage == "fingerprint"
    assert out[0].strategy_id.startswith("fingerprint.")
    assert out[0].locator.kind in {"xpath", "css", "role", "text", "pw"}
    assert (out[0].score or 0.0) >= 0.75
