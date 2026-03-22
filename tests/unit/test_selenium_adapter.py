import pytest

from adapters.selenium_python.adapter import SeleniumPythonAdapter, _text_xpath
from adapters.selenium_python.facade import SeleniumHealerFacade
from tests.unit.selenium_fakes import FakeSeleniumDriver, FakeSeleniumElement
from xpath_healer.core.config import HealerConfig, ValidatorConfig
from xpath_healer.core.models import Intent, LocatorSpec
from xpath_healer.core.validator import XPathValidator
from xpath_healer.store.memory_repository import InMemoryMetadataRepository


@pytest.mark.asyncio
async def test_selenium_validator_accepts_button_role_locator() -> None:
    driver = FakeSeleniumDriver()
    driver.add_element(
        FakeSeleniumElement(tag="button", text="Submit", attrs={"role": "button"}),
        selectors={"css selector": ["button", '[role="button"]']},
    )

    validator = XPathValidator(ValidatorConfig(), adapter=SeleniumPythonAdapter())
    result = await validator.validate_candidate(
        driver,
        LocatorSpec(kind="role", value="button", options={"name": "Submit", "exact": True}),
        field_type="button",
        intent=Intent(text="Submit", match_mode="exact"),
    )

    assert result.ok


@pytest.mark.asyncio
async def test_selenium_facade_recovers_with_attribute_strategy() -> None:
    driver = FakeSeleniumDriver()
    driver.add_element(
        FakeSeleniumElement(
            tag="input",
            attrs={"type": "text", "name": "username", "data-testid": "username-input"},
        ),
        selectors={
            "css selector": ['[data-testid="username-input"]', '[name="username"]', "input"],
            "xpath": ['//*[@name="username"]'],
        },
    )

    config = HealerConfig()
    config.adapter.name = "selenium_python"
    config.stages.page_index = False
    facade = SeleniumHealerFacade(config=config, repository=InMemoryMetadataRepository())

    recovered = await facade.recover_locator(
        page=driver,
        app_id="app",
        page_name="login",
        element_name="username",
        field_type="textbox",
        fallback=LocatorSpec(kind="xpath", value="//input[@id='missing-id']"),
        vars={"data-testid": "username-input", "label": "Username"},
    )

    assert recovered.status == "success"
    assert recovered.locator_spec is not None
    assert recovered.strategy_id in {"attribute", "metadata.last_good", "metadata.robust", "metadata.robust_xpath"}
    assert recovered.raw_locator is not None


def test_selenium_text_xpath_is_valid_relative_xpath() -> None:
    assert _text_xpath("Vega", exact=True) == (
        "descendant-or-self::*[normalize-space(.) = 'Vega' and not(.//*[normalize-space(.) = 'Vega'])]"
    )
    assert "descendant-or-self::*" in _text_xpath("Vega", exact=False)


@pytest.mark.asyncio
async def test_selenium_role_locator_uses_associated_label_name() -> None:
    driver = FakeSeleniumDriver()
    driver.add_element(
        FakeSeleniumElement(
            tag="input",
            attrs={"type": "checkbox", "data-label": "Home"},
        ),
        selectors={
            "css selector": ['input[type="checkbox"]'],
        },
    )

    validator = XPathValidator(ValidatorConfig(), adapter=SeleniumPythonAdapter())
    result = await validator.validate_candidate(
        driver,
        LocatorSpec(kind="role", value="checkbox", options={"name": "Home", "exact": True}),
        field_type="checkbox",
        intent=Intent(label="Home", text="Home"),
    )

    assert result.ok
