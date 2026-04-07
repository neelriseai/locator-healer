Title: Integration and Automation Layer Architecture Prompt

Layer objective:
- Validate full healing behavior in browser-driven scenarios with auditable artifacts.

Mandatory reference:
- `prompts/final_solution_pack/08_Algorithm_Inventory.md` (section 8)

Use this prompt with AI assistant:

1. Build integration layer using pytest-bdd + Playwright and pytest + Selenium.
2. Define scenarios with intentionally broken fallback locators.
3. Call healer facade during runtime step actions.
4. Validate business outcomes and healing stage traces.
5. Capture artifact evidence per step and per test.

Runtime model requirements:
1. Playwright path remains async-native.
2. Selenium path preserves `asyncio.to_thread` wrapper behavior for blocking webdriver calls.
3. Both paths must support common locator kinds/options and validator expectations.

Primary files:
1. `tests/integration/features/demo_qa_healing.feature`
2. `tests/integration/test_demo_qa_healing_bdd.py`
3. `tests/integration/test_demo_qa_healing_selenium.py`
4. `tests/integration/conftest.py`
5. `tests/integration/settings.py`
6. `tests/integration/config.json`
7. `adapters/playwright_python/{adapter.py,facade.py}`
8. `adapters/selenium_python/{adapter.py,facade.py}`

Acceptance criteria:
1. Scenarios execute in configured browser mode.
2. Healing traces are available for each healed element.
3. Reports and media artifacts are generated for investigation.
4. Adapter behavior is parity-checked between Playwright and Selenium.
