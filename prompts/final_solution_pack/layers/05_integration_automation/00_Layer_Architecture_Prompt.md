Title: Integration and Automation Layer Architecture Prompt

Layer objective:
- Validate full healing behavior in browser-driven BDD scenarios with auditable artifacts.

Use this prompt with AI assistant:

1. Build integration layer using pytest-bdd and Playwright.
2. Define scenarios with intentionally broken fallback locators.
3. Call healer facade during runtime step actions.
4. Validate business outcomes and healing stage traces.
5. Capture artifact evidence per step and per test.

Primary files:
1. `tests/integration/features/demo_qa_healing.feature`
2. `tests/integration/test_demo_qa_healing_bdd.py`
3. `tests/integration/conftest.py`
4. `tests/integration/settings.py`
5. `tests/integration/config.json`

Acceptance criteria:
1. Scenarios execute in configured browser mode.
2. Healing traces are available for each healed element.
3. Reports and media artifacts are generated for investigation.

