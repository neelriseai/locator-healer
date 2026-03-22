import pytest

from tests.unit.fakes import FakeElement, FakePage
from xpath_healer.api.facade import XPathHealerFacade
from xpath_healer.core.config import HealerConfig
from xpath_healer.core.models import BuildInput, Intent, LocatorSpec
from xpath_healer.core.validator import ValidationResult
from xpath_healer.store.memory_repository import InMemoryMetadataRepository


@pytest.mark.asyncio
async def test_recover_with_attribute_then_metadata_reuse() -> None:
    page = FakePage()
    username = FakeElement(
        tag="input",
        text="",
        attrs={"type": "text", "name": "username", "data-testid": "username-input"},
    )
    page.add_element(username, selectors=['[data-testid="username-input"]', "input"])

    cfg = HealerConfig()
    cfg.stages.page_index = False
    facade = XPathHealerFacade(config=cfg, repository=InMemoryMetadataRepository())
    fallback = LocatorSpec(kind="xpath", value="//input[@id='missing-id']")

    first = await facade.recover_locator(
        page=page,
        app_id="app",
        page_name="login",
        element_name="username",
        field_type="textbox",
        fallback=fallback,
        vars={"data-testid": "username-input", "label": "Username"},
    )
    assert first.status == "success"
    assert first.locator_spec is not None
    assert first.strategy_id in {"attribute", "metadata.last_good", "metadata.robust", "metadata.robust_xpath"}

    second = await facade.recover_locator(
        page=page,
        app_id="app",
        page_name="login",
        element_name="username",
        field_type="textbox",
        fallback=fallback,
        vars={},
    )
    assert second.status == "success"
    assert second.strategy_id in {"metadata.last_good", "metadata.robust", "metadata.robust_xpath"}


@pytest.mark.asyncio
async def test_persisted_robust_xpath_prefers_successful_locator_when_signature_xpath_is_weak() -> None:
    page = FakePage()
    checkbox = FakeElement(tag="span", text="", attrs={"class": "rct-checkbox"})
    page.add_element(
        checkbox,
        selectors=[
            "xpath=//*[self::span or self::label][normalize-space()='Home']/preceding::*[contains(@class,'checkbox')][1]",
            "//*[self::span or self::label][normalize-space()='Home']/preceding::*[contains(@class,'checkbox')][1]",
            "span",
        ],
    )

    cfg = HealerConfig()
    cfg.stages.fallback = False
    cfg.stages.metadata = False
    cfg.stages.fingerprint = False
    cfg.stages.page_index = False
    cfg.stages.signature = False
    cfg.stages.dom_mining = False
    cfg.stages.defaults = False
    cfg.stages.position = False
    cfg.stages.rag = False
    facade = XPathHealerFacade(config=cfg, repository=InMemoryMetadataRepository())
    strong_xpath = "//*[self::span or self::label][normalize-space()='Home']/preceding::*[contains(@class,'checkbox')][1]"
    inp = BuildInput(
        page=page,
        app_id="app",
        page_name="checkbox",
        element_name="home_checkbox_icon",
        field_type="checkbox",
        fallback=LocatorSpec(kind="xpath", value="//input[@id='missing-id']"),
        vars={"label": "Home"},
        intent=Intent.from_vars({"label": "Home"}),
    )
    meta = await facade.healing_service._persist_success(
        facade.ctx,
        inp,
        LocatorSpec(kind="xpath", value=strong_xpath),
        strategy_id="checkbox_icon_by_label",
        validation=ValidationResult.success(matched_count=1, chosen_index=0, reason_codes=["validated_proxy_checkbox"]),
    )

    assert meta.locator_variants["robust_xpath"].value == strong_xpath
