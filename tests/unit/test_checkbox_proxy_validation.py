import pytest

from adapters.playwright_python.adapter import PlaywrightPythonAdapter
from tests.unit.fakes import FakeElement, FakePage
from xpath_healer.core.config import ValidatorConfig
from xpath_healer.core.models import Intent, LocatorSpec
from xpath_healer.core.strategies.checkbox_icon_by_label import CheckboxIconByLabelStrategy
from xpath_healer.core.validator import XPathValidator


@pytest.mark.asyncio
async def test_checkbox_proxy_class_is_accepted() -> None:
    page = FakePage()
    page.add_element(
        FakeElement(tag="span", text="", attrs={"class": "rct-checkbox"}),
        selectors=['[class="rct-checkbox"]'],
    )
    validator = XPathValidator(ValidatorConfig(), adapter=PlaywrightPythonAdapter())
    result = await validator.validate_candidate(
        page,
        LocatorSpec(kind="css", value='[class="rct-checkbox"]'),
        field_type="checkbox",
        intent=Intent(label="Home"),
    )
    assert result.ok
    assert "validated_proxy_checkbox" in result.reason_codes


@pytest.mark.asyncio
async def test_checkbox_icon_strategy_builds_candidates() -> None:
    strategy = CheckboxIconByLabelStrategy()
    assert strategy.supports("checkbox", {"label": "Home"})
    assert not strategy.supports("textbox", {"label": "Home"})


@pytest.mark.asyncio
async def test_checkbox_label_proxy_is_accepted() -> None:
    page = FakePage()
    page.add_element(
        FakeElement(
            tag="label",
            text="Home",
            attrs={
                "data-control-tag": "input",
                "data-control-type": "checkbox",
                "data-control-role": "checkbox",
            },
        ),
        selectors=["label"],
    )
    validator = XPathValidator(ValidatorConfig(), adapter=PlaywrightPythonAdapter())
    result = await validator.validate_candidate(
        page,
        LocatorSpec(kind="text", value="Home", options={"exact": False}),
        field_type="checkbox",
        intent=Intent(label="Home", text="Home"),
    )
    assert result.ok
    assert "validated_label_proxy_toggle" in result.reason_codes


@pytest.mark.asyncio
async def test_checkbox_text_inside_label_proxy_is_accepted() -> None:
    page = FakePage()
    page.add_element(
        FakeElement(
            tag="span",
            text="Home",
            attrs={
                "data-proxy-label-tag": "label",
                "data-proxy-label-text": "Home",
                "data-proxy-control-tag": "input",
                "data-proxy-control-type": "checkbox",
                "data-proxy-control-role": "checkbox",
            },
        ),
        selectors=["span"],
    )
    validator = XPathValidator(ValidatorConfig(), adapter=PlaywrightPythonAdapter())
    result = await validator.validate_candidate(
        page,
        LocatorSpec(kind="text", value="Home", options={"exact": False}),
        field_type="checkbox",
        intent=Intent(label="Home", text="Home"),
    )
    assert result.ok
    assert "validated_label_proxy_toggle" in result.reason_codes
