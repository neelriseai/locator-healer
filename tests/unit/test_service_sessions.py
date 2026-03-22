import pytest

pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient

from adapters.selenium_python.facade import SeleniumHealerFacade
from service.main import create_app
from service.session_registry import AutomationSessionRegistry
from tests.unit.selenium_fakes import FakeSeleniumDriver, FakeSeleniumElement

def _selenium_driver() -> FakeSeleniumDriver:
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
    return driver


def test_heal_endpoint_resolves_selenium_session_from_registry() -> None:
    registry = AutomationSessionRegistry()
    registry.register("selenium-session", _selenium_driver())
    app = create_app(facade=SeleniumHealerFacade(), session_registry=registry)
    client = TestClient(app)

    payload = {
        "session_id": "selenium-session",
        "app_id": "app",
        "page_name": "login",
        "element_name": "username",
        "field_type": "textbox",
        "fallback": {"kind": "xpath", "value": "//input[@id='missing-id']"},
        "vars": {"data-testid": "username-input", "label": "Username"},
    }
    response = client.post("/heal", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["locator_spec"]["kind"] == "css"


def test_heal_endpoint_supports_sync_resolver_callback() -> None:
    driver = _selenium_driver()

    def _resolver(session_id: str):  # noqa: ANN202
        return driver if session_id == "sync-selenium" else None

    app = create_app(facade=SeleniumHealerFacade(), page_resolver=_resolver)
    client = TestClient(app)

    payload = {
        "session_id": "sync-selenium",
        "app_id": "app",
        "page_name": "login",
        "element_name": "username",
        "field_type": "textbox",
        "fallback": {"kind": "xpath", "value": "//input[@id='missing-id']"},
        "vars": {"data-testid": "username-input", "label": "Username"},
    }
    response = client.post("/heal", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "success"
