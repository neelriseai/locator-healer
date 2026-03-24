"""BDD integration tests using Playwright + XPathHealer recover flow."""

from __future__ import annotations

from typing import Any
import logging
import json
from datetime import UTC, datetime

import pytest

pytest.importorskip("pytest_bdd")
pytest.importorskip("playwright.async_api")

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from pytest_bdd import given, parsers, scenarios, then, when

from xpath_healer.api.facade import XPathHealerFacade
from xpath_healer.core.models import LocatorSpec, Recovered
from xpath_healer.store.repository import MetadataRepository
from tests.integration.conftest import AsyncRuntime
from tests.integration.settings import IntegrationSettings


APP_ID = "demo-qa-app"

pytestmark = [pytest.mark.integration]

scenarios("features/demo_qa_healing.feature")


@pytest.fixture
def healer(metadata_repository: MetadataRepository) -> XPathHealerFacade:
    return XPathHealerFacade(repository=metadata_repository)


@pytest.fixture
def scenario_state(healer: XPathHealerFacade) -> dict[str, Any]:
    repo = healer.repository
    if hasattr(repo, "events"):
        repo.events.clear()
    return {"recovered": {}, "locators": {}, "healed": []}


def _append_jsonl(path: Any, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True, default=str))
        fh.write("\n")


def _capture_dom_paths(runtime: AsyncRuntime, locator: Any) -> dict[str, str]:
    try:
        count = runtime.run(locator.count())
        if count <= 0:
            return {}
        target = locator.nth(0)
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


def _broken_fallback(name: str) -> LocatorSpec:
    return LocatorSpec(kind="xpath", value=f"//xh-never-match[@id='{name}-broken']")


def _heal(
    runtime: AsyncRuntime,
    state: dict[str, Any],
    page: Page,
    healer: XPathHealerFacade,
    integration_logger: logging.Logger,
    integration_settings: IntegrationSettings,
    page_name: str,
    element_name: str,
    field_type: str,
    vars_map: dict[str, str],
) -> Any:
    fallback = _broken_fallback(element_name)
    recovered: Recovered = runtime.run(
        healer.recover_locator(
            page=page,
            app_id=APP_ID,
            page_name=page_name,
            element_name=element_name,
            field_type=field_type,
            fallback=fallback,
            vars=vars_map,
        )
    )
    healed_value = recovered.locator_spec.value if recovered.locator_spec else None
    healed_kind = recovered.locator_spec.kind if recovered.locator_spec else None
    trace_summary = [f"{entry.stage}:{entry.strategy_id}:{entry.status}" for entry in recovered.trace]
    quality = recovered.metadata.quality_metrics if recovered.metadata else {}
    integration_logger.info(
        "heal_attempt element=%s field_type=%s status=%s strategy=%s correlation_id=%s fallback_xpath=%s healed_kind=%s healed_value=%s uniqueness=%s stability=%s similarity=%s overall=%s",
        element_name,
        field_type,
        recovered.status,
        recovered.strategy_id,
        recovered.correlation_id,
        fallback.value,
        healed_kind,
        healed_value,
        quality.get("uniqueness_score"),
        quality.get("stability_score"),
        quality.get("similarity_score"),
        quality.get("overall_score"),
    )
    _append_jsonl(
        integration_settings.healing_calls_jsonl,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "app_id": APP_ID,
            "page_name": page_name,
            "element_name": element_name,
            "field_type": field_type,
            "fallback_xpath": fallback.value,
            "status": recovered.status,
            "strategy_id": recovered.strategy_id,
            "correlation_id": recovered.correlation_id,
            "healed_locator_kind": healed_kind,
            "healed_locator_value": healed_value,
            "uniqueness_score": quality.get("uniqueness_score"),
            "stability_score": quality.get("stability_score"),
            "similarity_score": quality.get("similarity_score"),
            "overall_score": quality.get("overall_score"),
            "matched_count": quality.get("matched_count"),
            "trace": trace_summary,
        },
    )
    assert recovered.status == "success", f"Healing failed for {element_name}: {recovered.to_dict()}"
    assert recovered.locator_spec is not None
    state["recovered"][element_name] = recovered
    state["healed"].append(
        {
            "page_name": page_name,
            "element_name": element_name,
            "strategy_id": recovered.strategy_id,
            "locator_kind": recovered.locator_spec.kind,
            "locator_value": recovered.locator_spec.value,
        }
    )
    locator = recovered.playwright_locator
    state["locators"][element_name] = locator
    live_paths = _capture_dom_paths(runtime, locator)

    variants: dict[str, Any] = {}
    if recovered.metadata and recovered.metadata.locator_variants:
        variants = recovered.metadata.locator_variants

    selected_locator_kind = recovered.locator_spec.kind
    selected_locator_value = recovered.locator_spec.value

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

    integration_logger.info(
        "healed_paths element=%s selected_kind=%s selected_value=%s xpath=%s xpath_source=%s css=%s css_source=%s",
        element_name,
        selected_locator_kind,
        selected_locator_value,
        healed_xpath,
        healed_xpath_source,
        healed_css,
        healed_css_source,
    )
    _append_jsonl(
        integration_settings.healing_calls_jsonl,
        {
            "timestamp": datetime.now(UTC).isoformat(),
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
    return locator


@given(parsers.parse('I open the "{page_path}" demo page'))
def open_demo_page(
    runtime: AsyncRuntime,
    page: Page,
    scenario_state: dict[str, Any],
    page_path: str,
    integration_settings: IntegrationSettings,
) -> None:
    url = f"{integration_settings.base_url}/{page_path}"
    scenario_state["current_page"] = page_path
    try:
        runtime.run(page.goto(url, wait_until="domcontentloaded"))
    except PlaywrightTimeoutError as exc:
        pytest.skip(f"Could not open {url}: {exc}")
    except Exception as exc:
        pytest.skip(f"Could not open {url}: {exc}")


@when("I heal and fill all text-box form fields")
def heal_and_fill_text_box(
    runtime: AsyncRuntime,
    page: Page,
    healer: XPathHealerFacade,
    scenario_state: dict[str, Any],
    integration_logger: logging.Logger,
    integration_settings: IntegrationSettings,
) -> None:
    full_name = _heal(
        runtime,
        scenario_state,
        page,
        healer,
        integration_logger,
        integration_settings,
        page_name="text_box",
        element_name="full_name",
        field_type="textbox",
        vars_map={"label": "Full Name", "name": "userName", "axisHint": "following", "strict_single_match": "false"},
    )
    email = _heal(
        runtime,
        scenario_state,
        page,
        healer,
        integration_logger,
        integration_settings,
        page_name="text_box",
        element_name="email",
        field_type="textbox",
        vars_map={"label": "Email", "name": "userEmail", "axisHint": "following", "strict_single_match": "false"},
    )
    current_address = _heal(
        runtime,
        scenario_state,
        page,
        healer,
        integration_logger,
        integration_settings,
        page_name="text_box",
        element_name="current_address",
        field_type="textbox",
        vars_map={"label": "Current Address", "axisHint": "following", "strict_single_match": "false"},
    )
    permanent_address = _heal(
        runtime,
        scenario_state,
        page,
        healer,
        integration_logger,
        integration_settings,
        page_name="text_box",
        element_name="permanent_address",
        field_type="textbox",
        vars_map={"label": "Permanent Address", "axisHint": "following", "strict_single_match": "false"},
    )

    runtime.run(full_name.fill("Neela User"))
    runtime.run(email.fill("neela.user@example.com"))
    runtime.run(current_address.fill("Bangalore, India"))
    runtime.run(permanent_address.fill("Mysuru, India"))


@when("I heal and click the text-box submit button")
def heal_and_click_submit(
    runtime: AsyncRuntime,
    page: Page,
    healer: XPathHealerFacade,
    scenario_state: dict[str, Any],
    integration_logger: logging.Logger,
    integration_settings: IntegrationSettings,
) -> None:
    submit = _heal(
        runtime,
        scenario_state,
        page,
        healer,
        integration_logger,
        integration_settings,
        page_name="text_box",
        element_name="submit",
        field_type="button",
        vars_map={"text": "Submit", "match_mode": "exact", "strict_single_match": "false"},
    )
    runtime.run(submit.scroll_into_view_if_needed())
    try:
        runtime.run(submit.click())
    except Exception:
        runtime.run(submit.evaluate("el => el.click()"))


@then("I should see submitted text-box output values")
def verify_submitted_output(runtime: AsyncRuntime, page: Page) -> None:
    output = page.locator("#output")
    assert runtime.run(output.count()) > 0
    text = runtime.run(output.inner_text()).casefold()
    assert "neela user" in text
    assert "neela.user@example.com" in text
    assert "bangalore, india" in text
    assert "mysuru, india" in text


@when("I heal and click the Home checkbox icon")
def heal_and_click_home_checkbox_icon(
    runtime: AsyncRuntime,
    page: Page,
    healer: XPathHealerFacade,
    scenario_state: dict[str, Any],
    integration_logger: logging.Logger,
    integration_settings: IntegrationSettings,
) -> None:
    checkbox_icon = _heal(
        runtime,
        scenario_state,
        page,
        healer,
        integration_logger,
        integration_settings,
        page_name="checkbox",
        element_name="home_checkbox_icon",
        field_type="checkbox",
        vars_map={
            "label": "Home",
            "text": "Home",
            "strict_single_match": "false",
            "target": "icon",
        },
    )
    runtime.run(checkbox_icon.click())


@then("I should see checkbox selection message for Home")
def verify_checkbox_message(runtime: AsyncRuntime, page: Page) -> None:
    result = page.locator("#result")
    assert runtime.run(result.count()) > 0
    text = runtime.run(result.inner_text()).casefold()
    assert "you have selected" in text
    assert "home" in text


@when(parsers.parse('I heal and verify the first row first name is "{first_name}"'))
def verify_row_first_name(
    runtime: AsyncRuntime,
    page: Page,
    healer: XPathHealerFacade,
    scenario_state: dict[str, Any],
    integration_logger: logging.Logger,
    integration_settings: IntegrationSettings,
    first_name: str,
) -> None:
    first_name_locator = _heal(
        runtime,
        scenario_state,
        page,
        healer,
        integration_logger,
        integration_settings,
        page_name="webtables",
        element_name="row1_first_name",
        field_type="text",
        vars_map={
            "text": first_name,
            "match_mode": "exact",
            "occurrence": "0",
            "allow_position": "true",
            "strict_single_match": "false",
        },
    )
    assert runtime.run(first_name_locator.count()) > 0


@then("I heal and verify the first row last name is one of:")
def verify_row_last_name_from_table(
    runtime: AsyncRuntime,
    page: Page,
    healer: XPathHealerFacade,
    scenario_state: dict[str, Any],
    integration_logger: logging.Logger,
    integration_settings: IntegrationSettings,
    datatable: list[dict[str, str]],
) -> None:
    if datatable and isinstance(datatable[0], list):
        headers = datatable[0]
        try:
            idx = headers.index("last_name")
        except ValueError:
            idx = 0
        candidates = [row[idx] for row in datatable[1:] if len(row) > idx and row[idx]]
    else:
        candidates = [row["last_name"] for row in datatable]
    found = None
    for candidate in candidates:
        try:
            locator = _heal(
                runtime,
                scenario_state,
                page,
                healer,
                integration_logger,
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
            if runtime.run(locator.count()) > 0:
                found = candidate
                break
        except AssertionError:
            continue
    assert found is not None, f"Could not heal last name from candidates: {candidates}"


@when("I query raw invalid fallback xpath without healer")
def query_raw_invalid_fallback_without_healer(
    runtime: AsyncRuntime,
    page: Page,
    scenario_state: dict[str, Any],
    integration_logger: logging.Logger,
) -> None:
    raw_xpath = _broken_fallback("raw_xpath_negative").value
    count = runtime.run(page.locator(f"xpath={raw_xpath}").count())
    scenario_state["raw_xpath"] = raw_xpath
    scenario_state["raw_xpath_count"] = count
    integration_logger.error("raw_xpath_lookup_failed xpath=%s matched_count=%s", raw_xpath, count)


@then("report and logs should show xpath failure reason")
def report_and_logs_should_show_xpath_failure_reason(
    scenario_state: dict[str, Any],
    integration_logger: logging.Logger,
    integration_settings: IntegrationSettings,
) -> None:
    raw_xpath = scenario_state.get("raw_xpath")
    count = scenario_state.get("raw_xpath_count")
    assert raw_xpath, "Missing raw xpath in scenario state."
    assert count == 0, f"Expected invalid raw xpath to match 0 elements, got {count}"
    _append_jsonl(
        integration_settings.healing_calls_jsonl,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "app_id": APP_ID,
            "page_name": scenario_state.get("current_page"),
            "element_name": "raw_xpath_negative",
            "status": "failed_without_healer",
            "fallback_xpath": raw_xpath,
            "reason": "raw_xpath_no_match",
            "matched_count": count,
        },
    )
    pytest.fail(f"Intentional failure: raw fallback xpath did not resolve any element: {raw_xpath}")


@then("trace logs should contain expected healing stages")
def verify_trace_stages(scenario_state: dict[str, Any], healer: XPathHealerFacade) -> None:
    recovered_by_element: dict[str, Recovered] = scenario_state["recovered"]
    assert recovered_by_element, "No healed elements captured for trace verification."
    stages_cfg = healer.config.stages
    deterministic_enabled = any(
        [
            stages_cfg.fallback,
            stages_cfg.metadata,
            stages_cfg.rules,
            stages_cfg.fingerprint,
            getattr(stages_cfg, "page_index", False),
            stages_cfg.signature,
            stages_cfg.dom_mining,
            stages_cfg.defaults,
            stages_cfg.position,
        ]
    )
    model_only_mode = bool(stages_cfg.rag) and not deterministic_enabled
    expected_first_stage = "rag" if model_only_mode else "fallback"

    for element_name, recovered in recovered_by_element.items():
        trace = recovered.trace
        assert trace, f"Trace is empty for {element_name}"
        assert trace[0].stage == expected_first_stage, (
            f"First stage should be {expected_first_stage} for {element_name}"
        )
        if expected_first_stage == "fallback":
            assert trace[0].status == "fail", f"Fallback must fail for intentionally broken locator: {element_name}"

        ok_entries = [entry for entry in trace if entry.status == "ok"]
        assert ok_entries, f"No successful stage found in trace for {element_name}"
        if model_only_mode:
            assert any(entry.stage == "rag" for entry in ok_entries)
        else:
            assert any(
                entry.stage in {"rules", "defaults", "metadata", "signature", "dom_mining", "position", "page_index"}
                for entry in ok_entries
            )
        assert any(entry.strategy_id == recovered.strategy_id for entry in ok_entries), (
            f"Recovered strategy {recovered.strategy_id} not found among successful trace entries for {element_name}"
        )

        for entry in trace:
            assert entry.stage
            assert entry.strategy_id
            assert entry.status in {"ok", "fail"}

    repo = healer.repository
    if hasattr(repo, "events"):
        assert repo.events, "Expected structured events to be persisted in repository."
        stage_names = {event.get("stage") for event in repo.events}
        assert "recover_start" in stage_names
        assert "recover_end" in stage_names
        if model_only_mode:
            assert "rag" in stage_names
        else:
            assert "fallback" in stage_names
