import pytest

from adapters.playwright_python.adapter import PlaywrightPythonAdapter
from tests.unit.fakes import FakeElement, FakePage
from xpath_healer.core.config import ValidatorConfig
from xpath_healer.core.models import Intent, LocatorSpec
from xpath_healer.core.validator import XPathValidator


@pytest.mark.asyncio
async def test_button_validation_passes_on_text_match() -> None:
    page = FakePage()
    page.add_element(FakeElement(tag="button", text="Submit", attrs={"role": "button"}), selectors=["button"])
    validator = XPathValidator(ValidatorConfig(), adapter=PlaywrightPythonAdapter())

    result = await validator.validate_candidate(
        page,
        LocatorSpec(kind="role", value="button", options={"name": "Submit", "exact": True}),
        field_type="button",
        intent=Intent(text="Submit", match_mode="exact"),
    )

    assert result.ok


@pytest.mark.asyncio
async def test_strict_single_match_rejects_ambiguous_locator() -> None:
    page = FakePage()
    first = FakeElement(tag="input", text="", attrs={"name": "a", "type": "text"})
    second = FakeElement(tag="input", text="", attrs={"name": "b", "type": "text"})
    page.add_element(first, selectors=["input"])
    page.add_element(second, selectors=["input"])
    validator = XPathValidator(ValidatorConfig(strict_single_match=True), adapter=PlaywrightPythonAdapter())

    result = await validator.validate_candidate(
        page,
        LocatorSpec(kind="css", value="input"),
        field_type="textbox",
        intent=Intent(),
    )
    assert not result.ok
    assert "multiple_matches" in result.reason_codes


@pytest.mark.asyncio
async def test_textbox_validation_rejects_button() -> None:
    page = FakePage()
    page.add_element(FakeElement(tag="button", text="Run", attrs={"role": "button"}), selectors=["button"])
    validator = XPathValidator(ValidatorConfig(), adapter=PlaywrightPythonAdapter())

    result = await validator.validate_candidate(
        page,
        LocatorSpec(kind="css", value="button"),
        field_type="textbox",
        intent=Intent(),
    )
    assert not result.ok
    assert "type_mismatch_textbox" in result.reason_codes
