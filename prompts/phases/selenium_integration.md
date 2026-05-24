Title: Phase Prompt - Selenium Integration

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Integrate runtime healing into Selenium tests with adapter parity and correct async/thread model.

Prompt to use with AI assistant:

```
Implement Selenium integration for XPath Healer.

Scope:
- adapters/selenium_python/adapter.py
- adapters/selenium_python/facade.py
- tests/integration/test_demo_qa_healing_selenium.py
- tests/integration/conftest.py
- tests/integration/settings.py
- tests/integration/config.json

Required integration behavior:
1. Use intentionally broken fallback locators in test data.
2. Call `SeleniumHealerFacade.recover_locator(...)` during scenario steps.
3. Resolve selected locator through Selenium runtime adapter and continue assertions.
4. Emit logs + healing-call JSONL + cucumber/junit reports.
5. Keep stage-trace assertions profile-aware.

Adapter requirements:
1. Keep locator-kind parity with Playwright adapter: `css`, `xpath`, `role`, `text`, `pw`.
2. Support options: `exact`, `first`, `last`, `nth`, `has_text`.
3. Preserve validator contract methods:
   - `count`, `nth`, `is_visible`, `is_enabled`, `evaluate`, `bounding_box`
4. Use thread offload for blocking webdriver calls via `asyncio.to_thread`.
5. Keep stale-element read retry behavior in runtime locator element resolution.

Required artifacts:
- artifacts/logs/integration.log
- artifacts/logs/healing-flow.log
- artifacts/reports/cucumber-selenium.json
- artifacts/reports/integration-selenium-junit.xml
- artifacts/reports/healing-calls.jsonl
- artifacts/screenshots/*

Deliverables:
- Selenium adapter + facade updates.
- Selenium integration scenarios/fixtures.
- Env-driven browser/headless/binary configuration.
```

Acceptance criteria:
- Selenium integration tests run and generate artifacts.
- Healing traces are inspectable per element.
- Adapter behavior stays compatible with validator and core orchestration.

Validation command:
- `python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_selenium.py --cucumberjson=artifacts/reports/cucumber-selenium.json --junitxml=artifacts/reports/integration-selenium-junit.xml`
