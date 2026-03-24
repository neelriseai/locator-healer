"""Browser-backed Selenium integration coverage for healing flows."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("selenium")

from selenium import webdriver
from selenium.webdriver.common.by import By

from adapters.selenium_python.facade import SeleniumHealerFacade
from tests.integration.conftest import AsyncRuntime
from tests.integration.settings import IntegrationSettings
from xpath_healer.core.models import LocatorSpec, Recovered
from xpath_healer.store.repository import MetadataRepository


APP_ID = "demo-qa-app"

pytestmark = [pytest.mark.integration]


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True, default=str))
        fh.write("\n")


def _broken_fallback(name: str) -> LocatorSpec:
    return LocatorSpec(kind="xpath", value=f"//xh-never-match[@id='{name}-broken']")


def _chrome_driver(settings: IntegrationSettings) -> Any:
    base_args = [
        "--window-size=1440,1200",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-gpu",
        "--remote-debugging-pipe",
    ]
    headless_variants = [["--headless"], ["--headless=new"]] if settings.headless else [[]]
    errors: list[str] = []
    for variant in headless_variants:
        options = webdriver.ChromeOptions()
        for arg in base_args + variant:
            options.add_argument(arg)
        if settings.selenium_binary_path:
            options.binary_location = settings.selenium_binary_path
        try:
            return webdriver.Chrome(options=options)
        except Exception as exc:
            errors.append(f"args={base_args + variant}: {exc}")
    raise RuntimeError("; ".join(errors))


def _edge_driver(settings: IntegrationSettings) -> Any:
    options = webdriver.EdgeOptions()
    if settings.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1200")
    return webdriver.Edge(options=options)


def _firefox_driver(settings: IntegrationSettings) -> Any:
    options = webdriver.FirefoxOptions()
    if settings.headless:
        options.add_argument("-headless")
    return webdriver.Firefox(options=options)


def _build_selenium_driver(settings: IntegrationSettings) -> Any:
    browser = (settings.selenium_browser or "chrome").strip().lower()
    factories = {
        "chrome": _chrome_driver,
        "chromium": _chrome_driver,
        "edge": _edge_driver,
        "msedge": _edge_driver,
        "firefox": _firefox_driver,
    }
    order = [browser] if browser in factories else []
    for fallback in ("chrome", "edge", "firefox"):
        if fallback not in order:
            order.append(fallback)

    errors: list[str] = []
    for key in order:
        try:
            return factories[key](settings)
        except Exception as exc:
            errors.append(f"{key}: {exc}")
    pytest.skip(f"Selenium browser unavailable: {'; '.join(errors)}")


@pytest.fixture
def selenium_driver(
    request: Any,
    integration_settings: IntegrationSettings,
    integration_logger: logging.Logger,
) -> Any:
    driver = _build_selenium_driver(integration_settings)
    driver.set_page_load_timeout(20)
    driver.implicitly_wait(2)
    try:
        if not integration_settings.headless:
            driver.maximize_window()
    except Exception:
        # Some driver/headless combinations may not support maximize.
        pass
    integration_logger.info(
        "browser_started framework=selenium browser=%s headless=%s binary=%s",
        integration_settings.selenium_browser,
        integration_settings.headless,
        integration_settings.selenium_binary_path or "",
    )
    try:
        yield driver
    finally:
        test_name = request.node.name
        if integration_settings.screenshot_each_test:
            final_path = integration_settings.screenshots_dir / f"{test_name}__selenium__final.png"
            try:
                driver.save_screenshot(str(final_path))
            except Exception:
                pass
        try:
            driver.quit()
        except Exception:
            pass


@pytest.fixture
def selenium_healer(metadata_repository: MetadataRepository) -> SeleniumHealerFacade:
    return SeleniumHealerFacade(repository=metadata_repository)


def _recover(
    runtime: AsyncRuntime,
    driver: Any,
    healer: SeleniumHealerFacade,
    integration_settings: IntegrationSettings,
    page_name: str,
    element_name: str,
    field_type: str,
    vars_map: dict[str, str],
) -> Recovered:
    fallback = _broken_fallback(element_name)
    recovered = runtime.run(
        healer.recover_locator(
            page=driver,
            app_id=APP_ID,
            page_name=page_name,
            element_name=element_name,
            field_type=field_type,
            fallback=fallback,
            vars=vars_map,
        )
    )
    assert recovered.status == "success", recovered.to_dict()
    _append_jsonl(
        integration_settings.healing_calls_jsonl,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "framework": "selenium_python",
            "page_name": page_name,
            "element_name": element_name,
            "field_type": field_type,
            "status": recovered.status,
            "strategy_id": recovered.strategy_id,
            "fallback_xpath": fallback.value,
            "healed_locator_kind": recovered.locator_spec.kind if recovered.locator_spec else None,
            "healed_locator_value": recovered.locator_spec.value if recovered.locator_spec else None,
        },
    )
    return recovered


def _first(runtime_locator: Any) -> Any:
    return runtime_locator.nth(0)


def test_selenium_text_box_form_fill_and_submit(
    runtime: AsyncRuntime,
    selenium_driver: Any,
    selenium_healer: SeleniumHealerFacade,
    integration_settings: IntegrationSettings,
) -> None:
    selenium_driver.get(f"{integration_settings.base_url}/text-box")

    _first(
        _recover(
            runtime,
            selenium_driver,
            selenium_healer,
            integration_settings,
            page_name="text_box",
            element_name="full_name",
            field_type="textbox",
            vars_map={"label": "Full Name", "name": "userName", "axisHint": "following", "strict_single_match": "false"},
        ).runtime_locator
    ).send_keys("Neela User")
    _first(
        _recover(
            runtime,
            selenium_driver,
            selenium_healer,
            integration_settings,
            page_name="text_box",
            element_name="email",
            field_type="textbox",
            vars_map={"label": "Email", "name": "userEmail", "axisHint": "following", "strict_single_match": "false"},
        ).runtime_locator
    ).send_keys("neela.user@example.com")
    _first(
        _recover(
            runtime,
            selenium_driver,
            selenium_healer,
            integration_settings,
            page_name="text_box",
            element_name="current_address",
            field_type="textbox",
            vars_map={"label": "Current Address", "axisHint": "following", "strict_single_match": "false"},
        ).runtime_locator
    ).send_keys("Bangalore, India")
    _first(
        _recover(
            runtime,
            selenium_driver,
            selenium_healer,
            integration_settings,
            page_name="text_box",
            element_name="permanent_address",
            field_type="textbox",
            vars_map={"label": "Permanent Address", "axisHint": "following", "strict_single_match": "false"},
        ).runtime_locator
    ).send_keys("Mysuru, India")

    submit_locator = _recover(
        runtime,
        selenium_driver,
        selenium_healer,
        integration_settings,
        page_name="text_box",
        element_name="submit",
        field_type="button",
        vars_map={"text": "Submit", "match_mode": "exact", "strict_single_match": "false"},
    ).runtime_locator.nth(0)
    runtime.run(
        submit_locator.evaluate(
            "el => { el.scrollIntoView({block: 'center', inline: 'nearest'}); return true; }"
        )
    )
    runtime.run(submit_locator.evaluate("el => { el.click(); return true; }"))

    output = selenium_driver.find_element(By.CSS_SELECTOR, "#output").text.casefold()
    assert "neela user" in output
    assert "neela.user@example.com" in output
    assert "bangalore, india" in output
    assert "mysuru, india" in output


def test_selenium_checkbox_home_icon_select_and_message_verify(
    runtime: AsyncRuntime,
    selenium_driver: Any,
    selenium_healer: SeleniumHealerFacade,
    integration_settings: IntegrationSettings,
) -> None:
    selenium_driver.get(f"{integration_settings.base_url}/checkbox")
    _first(
        _recover(
            runtime,
            selenium_driver,
            selenium_healer,
            integration_settings,
            page_name="checkbox",
            element_name="home_checkbox_icon",
            field_type="checkbox",
            vars_map={"label": "Home", "text": "Home", "strict_single_match": "false", "target": "icon"},
        ).runtime_locator
    ).click()
    message = selenium_driver.find_element(By.CSS_SELECTOR, "#result").text.casefold()
    assert "you have selected" in message
    assert "home" in message


def test_selenium_webtables_first_row_verification(
    runtime: AsyncRuntime,
    selenium_driver: Any,
    selenium_healer: SeleniumHealerFacade,
    integration_settings: IntegrationSettings,
) -> None:
    selenium_driver.get(f"{integration_settings.base_url}/webtables")
    first_name = _recover(
        runtime,
        selenium_driver,
        selenium_healer,
        integration_settings,
        page_name="webtables",
        element_name="row1_first_name",
        field_type="text",
        vars_map={
            "text": "Cierra",
            "match_mode": "exact",
            "occurrence": "0",
            "allow_position": "true",
            "strict_single_match": "false",
        },
    )
    assert runtime.run(first_name.runtime_locator.count()) > 0

    found_last_name = None
    for candidate in ("Veha", "Vega"):
        try:
            recovered = _recover(
                runtime,
                selenium_driver,
                selenium_healer,
                integration_settings,
                page_name="webtables",
                element_name=f"row1_last_name_{candidate.casefold()}",
                field_type="text",
                vars_map={
                    "text": candidate,
                    "match_mode": "exact",
                    "occurrence": "0",
                    "allow_position": "true",
                    "strict_single_match": "false",
                },
            )
        except AssertionError:
            continue
        if runtime.run(recovered.runtime_locator.count()) > 0:
            found_last_name = candidate
            break

    assert found_last_name is not None


def test_selenium_raw_invalid_fallback_without_healer(
    selenium_driver: Any,
    integration_settings: IntegrationSettings,
) -> None:
    selenium_driver.get(f"{integration_settings.base_url}/text-box")
    raw_xpath = _broken_fallback("raw_xpath_negative").value
    count = len(selenium_driver.find_elements(By.XPATH, raw_xpath))
    _append_jsonl(
        integration_settings.healing_calls_jsonl,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "framework": "selenium_python",
            "page_name": "text_box",
            "element_name": "raw_xpath_negative",
            "status": "failed_without_healer",
            "fallback_xpath": raw_xpath,
            "reason": "raw_xpath_no_match",
            "matched_count": count,
        },
    )
    assert count == 0
