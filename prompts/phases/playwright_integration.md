Title: Phase Prompt - Playwright + Pytest-BDD Integration

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Integrate runtime healing into browser tests with clear artifacts and stage trace visibility.

Prompt to use with AI assistant:

```
Implement Playwright integration for XPath Healer aligned with `prompts/01_Master_Design_for_xpath_healer.md`.

Scope:
- tests/integration/features/demo_qa_healing.feature
- tests/integration/test_demo_qa_healing_bdd.py
- tests/integration/conftest.py
- tests/integration/settings.py
- tests/integration/config.json

Required integration behavior:
1. Use broken fallback locators in test data.
2. Call `XPathHealerFacade.recover_locator(...)` during step execution.
3. Resolve selected locator to Playwright locator and continue actions/assertions.
4. Capture per-step screenshots and per-test video.
5. Emit healing-call records to report JSONL.
6. Assert stage traces according to active config profile.

Required artifacts:
- artifacts/logs/integration.log
- artifacts/logs/healing-flow.log
- artifacts/reports/cucumber.json
- artifacts/reports/integration-junit.xml
- artifacts/reports/healing-calls.jsonl
- artifacts/screenshots/*
- artifacts/videos/*

Deliverables:
- BDD feature scenarios.
- Step definitions and fixtures.
- Configuration toggles for headless/browser channel/screenshots/video.
```

Acceptance criteria:
- Integration tests run via pytest-bdd and produce expected artifacts.
- Healing traces are inspectable per element.
- Negative scenario without healer clearly fails and logs reason.

Validation command:
- `python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json`

