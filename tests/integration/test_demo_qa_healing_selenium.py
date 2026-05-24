"""Browser-backed Selenium integration coverage for healing flows."""

from __future__ import annotations

from contextlib import contextmanager
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


def _slug(value: str) -> str:
    out = []
    for ch in value:
        if ch.isalnum() or ch in "_.-":
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True, default=str))
        fh.write("\n")


def _broken_fallback(name: str) -> LocatorSpec:
    return LocatorSpec(kind="xpath", value=f"//xh-never-match[@id='{name}-broken']")


class SeleniumStepReporter:
    def __init__(
        self,
        request: Any,
        settings: IntegrationSettings,
        logger: logging.Logger,
        driver: Any,
    ) -> None:
        self.request = request
        self.settings = settings
        self.logger = logger
        self.driver = driver
        self._step_index = 0
        self._test_name = _slug(request.node.name)

    def _record(
        self,
        *,
        keyword: str,
        name: str,
        status: str,
        error: str | None = None,
    ) -> None:
        self._step_index += 1
        step_name = str(name or "step")
        step_slug = _slug(step_name)
        screenshot_path = None
        if self.settings.screenshot_each_step:
            suffix = "__error" if status == "failed" else ""
            screenshot_path = (
                self.settings.screenshots_dir
                / f"{self._test_name}__step{self._step_index:02d}__{step_slug}{suffix}.png"
            )
            try:
                self.driver.save_screenshot(str(screenshot_path))
                self.logger.info(
                    "step_screenshot_saved framework=selenium test=%s step=%s keyword=%s path=%s",
                    self._test_name,
                    step_slug,
                    keyword,
                    screenshot_path,
                )
            except Exception as exc:
                self.logger.error(
                    "step_screenshot_failed framework=selenium test=%s step=%s keyword=%s error=%s",
                    self._test_name,
                    step_slug,
                    keyword,
                    exc,
                )
                screenshot_path = None

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "framework": "selenium_python",
            "test": self.request.node.name,
            "scenario": self.request.node.name,
            "step_index": self._step_index,
            "step_keyword": keyword.strip(),
            "step_name": step_name,
            "status": status,
            "screenshot": str(screenshot_path) if screenshot_path else None,
        }
        if error:
            payload["error"] = error
        _append_jsonl(self.settings.step_report_jsonl, payload)

    @contextmanager
    def step(self, name: str, keyword: str = "Step") -> Any:
        try:
            yield
        except Exception as exc:
            self._record(keyword=keyword, name=name, status="failed", error=str(exc))
            raise
        self._record(keyword=keyword, name=name, status="passed")


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
    # Temporarily disable implicit polling wait for timing diagnostics.
    driver.implicitly_wait(0)
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


@pytest.fixture
def selenium_steps(
    request: Any,
    integration_settings: IntegrationSettings,
    integration_logger: logging.Logger,
    selenium_driver: Any,
) -> SeleniumStepReporter:
    return SeleniumStepReporter(
        request=request,
        settings=integration_settings,
        logger=integration_logger,
        driver=selenium_driver,
    )


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
    quality = recovered.metadata.quality_metrics if recovered.metadata else {}
    _append_jsonl(
        integration_settings.healing_calls_jsonl,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "framework": "selenium_python",
            "app_id": APP_ID,
            "page_name": page_name,
            "element_name": element_name,
            "field_type": field_type,
            "status": recovered.status,
            "strategy_id": recovered.strategy_id,
            "fallback_xpath": fallback.value,
            "healed_locator_kind": recovered.locator_spec.kind if recovered.locator_spec else None,
            "healed_locator_value": recovered.locator_spec.value if recovered.locator_spec else None,
            "uniqueness_score": quality.get("uniqueness_score"),
            "stability_score": quality.get("stability_score"),
            "similarity_score": quality.get("similarity_score"),
            "overall_score": quality.get("overall_score"),
            "matched_count": quality.get("matched_count"),
        },
    )

    live_paths = _capture_dom_paths(runtime, recovered.runtime_locator)
    variants: dict[str, Any] = {}
    if recovered.metadata and recovered.metadata.locator_variants:
        variants = recovered.metadata.locator_variants

    selected_locator_kind = recovered.locator_spec.kind if recovered.locator_spec else None
    selected_locator_value = recovered.locator_spec.value if recovered.locator_spec else None

    robust_xpath = variants["robust_xpath"].value if "robust_xpath" in variants else None
    robust_css = variants["robust_css"].value if "robust_css" in variants else None
    live_xpath = variants["live_xpath"].value if "live_xpath" in variants else live_paths.get("xpath")
    live_css = variants["live_css"].value if "live_css" in variants else live_paths.get("css")

    healed_xpath = None
    healed_xpath_source = None
    if selected_locator_kind == "xpath":
        healed_xpath = selected_locator_value
        healed_xpath_source = "selected_locator"
    elif robust_xpath:
        healed_xpath = robust_xpath
        healed_xpath_source = "metadata.robust_xpath"
    elif live_xpath:
        healed_xpath = live_xpath
        healed_xpath_source = "metadata.live_xpath" if "live_xpath" in variants else "dom.live_xpath"

    healed_css = None
    healed_css_source = None
    if selected_locator_kind == "css":
        healed_css = selected_locator_value
        healed_css_source = "selected_locator"
    elif robust_css:
        healed_css = robust_css
        healed_css_source = "metadata.robust_css"
    elif live_css:
        healed_css = live_css
        healed_css_source = "metadata.live_css" if "live_css" in variants else "dom.live_css"

    _append_jsonl(
        integration_settings.healing_calls_jsonl,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "framework": "selenium_python",
            "app_id": APP_ID,
            "page_name": page_name,
            "element_name": element_name,
            "field_type": field_type,
            "status": "resolved_paths",
            "selected_locator_kind": selected_locator_kind,
            "selected_locator_value": selected_locator_value,
            "healed_xpath": healed_xpath,
            "healed_xpath_source": healed_xpath_source,
            "healed_css": healed_css,
            "healed_css_source": healed_css_source,
            "robust_xpath": robust_xpath,
            "live_xpath": live_xpath,
            "robust_css": robust_css,
            "live_css": live_css,
        },
    )
    return recovered


def _first(runtime_locator: Any) -> Any:
    return runtime_locator.nth(0)


def _capture_dom_paths(runtime: AsyncRuntime, runtime_locator: Any) -> dict[str, str]:
    try:
        count = runtime.run(runtime_locator.count())
        if count <= 0:
            return {}
        target = runtime_locator.nth(0)
        payload = runtime.run(
            target.evaluate(
                """el => {
                    function xpathFor(node) {
                      if (!node || node.nodeType !== 1) return null;
                      if (node.id) return `//*[@id="${node.id}"]`;
                      const parts = [];
                      let cur = node;
                      while (cur && cur.nodeType === 1) {
                        let idx = 1;
                        let sib = cur.previousElementSibling;
                        while (sib) {
                          if (sib.tagName === cur.tagName) idx += 1;
                          sib = sib.previousElementSibling;
                        }
                        const tag = (cur.tagName || '').toLowerCase();
                        parts.unshift(`${tag}[${idx}]`);
                        cur = cur.parentElement;
                      }
                      return '/' + parts.join('/');
                    }
                    function cssFor(node) {
                      if (!node || node.nodeType !== 1) return null;
                      if (node.id) return `#${node.id}`;
                      const parts = [];
                      let cur = node;
                      while (cur && cur.nodeType === 1 && parts.length < 8) {
                        let part = (cur.tagName || '').toLowerCase();
                        let nth = 1;
                        let sib = cur.previousElementSibling;
                        while (sib) {
                          if (sib.tagName === cur.tagName) nth += 1;
                          sib = sib.previousElementSibling;
                        }
                        part += `:nth-of-type(${nth})`;
                        parts.unshift(part);
                        cur = cur.parentElement;
                      }
                      return parts.join(' > ');
                    }
                    return { xpath: xpathFor(el), css: cssFor(el) };
                }"""
            )
        )
        out: dict[str, str] = {}
        if payload and payload.get("xpath"):
            out["xpath"] = str(payload["xpath"])
        if payload and payload.get("css"):
            out["css"] = str(payload["css"])
        return out
    except Exception:
        return {}


def _safe_click(runtime: AsyncRuntime, runtime_locator: Any) -> None:
    target = runtime_locator.nth(0)
    try:
        target.click()
    except Exception:
        runtime.run(target.evaluate("el => { el.click(); return true; }"))


def _try_highlight_table_cell(
    runtime: AsyncRuntime,
    runtime_locator: Any,
    *,
    expected_text: str | None = None,
    hold_ms: int = 2000,
) -> None:
    try:
        count = runtime.run(runtime_locator.count())
        if count <= 0:
            return
        target = runtime_locator.nth(0)
        if expected_text:
            needle = expected_text.strip().casefold()
            for idx in range(count):
                current = runtime_locator.nth(idx)
                current_text = runtime.run(
                    current.evaluate("el => (el.innerText || el.textContent || '').trim()")
                )
                if str(current_text or "").strip().casefold() == needle:
                    target = current
                    break
        runtime.run(
            target.evaluate(
                """(el, meta) => {
                    const hold = (meta && Number(meta.hold_ms)) || 900;
                    const prevBg = el.style.backgroundColor;
                    const prevOutline = el.style.outline;
                    const prevOutlineOffset = el.style.outlineOffset;
                    const prevTransition = el.style.transition;
                    el.style.transition = 'background-color 120ms ease-in-out, outline 120ms ease-in-out';
                    el.style.backgroundColor = '#fff59d';
                    el.style.outline = '2px solid #fbc02d';
                    el.style.outlineOffset = '1px';
                    setTimeout(() => {
                      el.style.backgroundColor = prevBg;
                      el.style.outline = prevOutline;
                      el.style.outlineOffset = prevOutlineOffset;
                      el.style.transition = prevTransition;
                    }, hold);
                    return true;
                }""",
                {"hold_ms": hold_ms},
            )
        )
    except Exception:
        return


def test_selenium_text_box_form_fill_and_submit(
    runtime: AsyncRuntime,
    selenium_driver: Any,
    selenium_healer: SeleniumHealerFacade,
    integration_settings: IntegrationSettings,
    selenium_steps: SeleniumStepReporter,
) -> None:
    with selenium_steps.step("Open text-box demo page", "Given"):
        selenium_driver.get(f"{integration_settings.base_url}/text-box")

    with selenium_steps.step("Heal and fill Full Name", "When"):
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
    with selenium_steps.step("Heal and fill Email", "And"):
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
    with selenium_steps.step("Heal and fill Current Address", "And"):
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
    with selenium_steps.step("Heal and fill Permanent Address", "And"):
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

    with selenium_steps.step("Heal and click Submit", "And"):
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

    with selenium_steps.step("Verify submitted output", "Then"):
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
    selenium_steps: SeleniumStepReporter,
) -> None:
    with selenium_steps.step("Open checkbox demo page", "Given"):
        selenium_driver.get(f"{integration_settings.base_url}/checkbox")
    with selenium_steps.step("Heal and click Home expand button", "When"):
        home_expand_button = _recover(
            runtime,
            selenium_driver,
            selenium_healer,
            integration_settings,
            page_name="checkbox",
            element_name="home_expand_button",
            field_type="button",
            vars_map={
                "label": "Home",
                "text": "Toggle",
                "match_mode": "exact",
                "strict_single_match": "false",
                "target": "toggle",
            },
        ).runtime_locator
        _safe_click(runtime, home_expand_button)

    with selenium_steps.step("Heal and click Desktop checkbox icon", "And"):
        desktop_checkbox_icon = _recover(
            runtime,
            selenium_driver,
            selenium_healer,
            integration_settings,
            page_name="checkbox",
            element_name="desktop_checkbox_icon",
            field_type="checkbox",
            vars_map={
                "label": "Desktop",
                "text": "Desktop",
                "strict_single_match": "false",
                "target": "icon",
            },
        ).runtime_locator
        _safe_click(runtime, desktop_checkbox_icon)

    with selenium_steps.step("Heal and click Downloads expand button", "And"):
        downloads_expand_button = _recover(
            runtime,
            selenium_driver,
            selenium_healer,
            integration_settings,
            page_name="checkbox",
            element_name="downloads_expand_button",
            field_type="button",
            vars_map={
                "label": "Downloads",
                "text": "Toggle",
                "match_mode": "exact",
                "strict_single_match": "false",
                "target": "toggle",
            },
        ).runtime_locator
        _safe_click(runtime, downloads_expand_button)

    with selenium_steps.step("Heal and click Excel File.doc checkbox icon", "And"):
        excel_file_doc_checkbox_icon = _recover(
            runtime,
            selenium_driver,
            selenium_healer,
            integration_settings,
            page_name="checkbox",
            element_name="excel_file_doc_checkbox_icon",
            field_type="checkbox",
            vars_map={
                "label": "Excel File.doc",
                "text": "Excel File.doc",
                "strict_single_match": "false",
                "target": "icon",
            },
        ).runtime_locator
        _safe_click(runtime, excel_file_doc_checkbox_icon)

    with selenium_steps.step("Verify checkbox selection message", "Then"):
        message = selenium_driver.find_element(By.CSS_SELECTOR, "#result").text.casefold()
        assert "you have selected" in message
        assert "desktop" in message
        assert "excel" in message


def test_selenium_webtables_first_row_verification(
    runtime: AsyncRuntime,
    selenium_driver: Any,
    selenium_healer: SeleniumHealerFacade,
    integration_settings: IntegrationSettings,
    selenium_steps: SeleniumStepReporter,
) -> None:
    with selenium_steps.step("Open webtables demo page", "Given"):
        selenium_driver.get(f"{integration_settings.base_url}/webtables")
    with selenium_steps.step("Heal and verify first-name cell as Cierra", "When"):
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
        _try_highlight_table_cell(runtime, first_name.runtime_locator, expected_text="Cierra", hold_ms=2000)

    with selenium_steps.step("Heal and verify last-name cell from allowed values", "Then"):
        found_last_name = None
        for candidate in ("Vega",):
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
                _try_highlight_table_cell(runtime, recovered.runtime_locator, expected_text=candidate, hold_ms=2000)
                found_last_name = candidate
                break

        assert found_last_name is not None


def test_selenium_raw_invalid_fallback_without_healer(
    selenium_driver: Any,
    integration_settings: IntegrationSettings,
    selenium_steps: SeleniumStepReporter,
) -> None:
    with selenium_steps.step("Open text-box demo page for raw xpath negative test", "Given"):
        selenium_driver.get(f"{integration_settings.base_url}/text-box")
    with selenium_steps.step("Query raw invalid fallback xpath without healer", "When"):
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
    with selenium_steps.step("Intentional failure to validate negative path reporting", "Then"):
        pytest.fail(f"Intentional failure: raw fallback xpath did not resolve any element: {raw_xpath}")
