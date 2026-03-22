# Layer 5 Design: Testing and Automation

Date: 2026-03-02
Layer: Testing/Automation
Depends on: all layers

## 1) Objective
Validate full solution via unit, contract, integration, and BDD regression.

## 2) Existing BDD Scope
Feature: `tests/integration/features/demo_qa_healing.feature`
- TC1: text-box fill + submit
- TC2: checkbox Home icon select + message verify
- TC3: webtables first-row verification
- TC4: intentional negative raw invalid fallback xpath

## 3) Testing Code Graph

```text
pytest -> unit tests (core/store/rag)
pytest-bdd -> integration steps
  -> Playwright browser/page fixtures
  -> XPathHealerFacade recover calls
  -> artifacts (screenshots/videos/reports/logs/metadata)
```

## 4) Commands (Canonical)

### 4.1 Compile check
```powershell
python -m compileall -q .
```

### 4.2 Unit tests
```powershell
python -m pytest -q tests\unit
```

### 4.3 Integration BDD
```powershell
python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json
```

Expected baseline:
- `3 passed`
- `1 failed` (intentional TC4 negative)

## 5) Artifacts to Verify
- `artifacts/reports/integration-junit.xml`
- `artifacts/reports/cucumber.json`
- `artifacts/reports/steps.jsonl`
- `artifacts/reports/healing-calls.jsonl`
- `artifacts/reports/integration-report.html`
- `artifacts/logs/integration.log`
- `artifacts/logs/healing-flow.log`
- `artifacts/screenshots/*.png`
- `artifacts/videos/*.webm`

## 6) Exact Implementation Prompt (Testing)
```text
Implement full testing stack for xpath-healer.
1) Keep unit tests for core/store/rag modules.
2) Keep pytest-bdd integration feature with TC1..TC4.
3) Ensure broken fallback xpath is used to trigger healer in positive scenarios.
4) Ensure step screenshots and one video per test are captured.
5) Generate junit, cucumber json, steps jsonl, healing-calls jsonl, and custom html report.
6) Keep TC4 as intentional negative scenario to demonstrate raw xpath failure reporting.
7) Add contract tests for PG repository and API response schemas.
```

## 7) Release Exit Criteria
- All non-negative tests green.
- No high-severity defects open.
- Logs and reports include traceability from request to healed locator.
