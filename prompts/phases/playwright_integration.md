Title: Phase Prompt - Playwright + Pytest-BDD Integration

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Integrate runtime healing into Playwright BDD tests with auditable artifacts and Selenium parity checks.

Prompt to use with AI assistant:

```
Implement Playwright integration for XPath Healer.

Scope:
- tests/integration/features/demo_qa_healing.feature
- tests/integration/test_demo_qa_healing_bdd.py
- tests/integration/conftest.py
- tests/integration/settings.py
- tests/integration/config.json

Required integration behavior:
1. Use intentionally broken fallback locators in test data.
2. Call `XPathHealerFacade.recover_locator(...)` during step execution.
3. Resolve healed locator to Playwright runtime locator and continue assertions.
4. Capture screenshots/video based on env-config capture flags.
5. Emit healing-call records to JSONL report.
6. Assert stage traces according to active profile/toggles.

Adapter/runtime notes:
1. Keep Playwright path async-native.
2. Keep scenario behavior parity with Selenium coverage for equivalent flows.
3. Keep negative-path scenario intentionally failing without healer and logging reason.

Required artifacts:
- artifacts/logs/integration.log
- artifacts/logs/healing-flow.log
- artifacts/reports/cucumber.json
- artifacts/reports/integration-junit.xml
- artifacts/reports/healing-calls.jsonl
- artifacts/screenshots/*
- artifacts/videos/*
```

Acceptance criteria:
- Integration tests run via pytest-bdd and produce expected artifacts.
- Healing traces are inspectable per healed element.
- Playwright behavior aligns with Selenium expectations for equivalent scenarios.

Validation command:
- `python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json --junitxml=artifacts/reports/integration-junit.xml`
