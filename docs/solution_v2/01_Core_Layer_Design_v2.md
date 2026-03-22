# Layer 1 Design: Core XPath-Healer (Deterministic Engine)

Date: 2026-03-02
Layer: Core
Depends on: setup only
Required by: DB, Service, Model, Testing

## 1) Objective
Build standalone healer core that can recover broken locators using deterministic strategy cascade.

## 2) Tech Stack
- Python 3.11+
- Playwright async locator API
- dataclasses for domain models
- pytest for unit tests

## 3) Files and Methods (Exact)
- `xpath_healer/core/models.py`
  - `LocatorSpec`, `HealingHints`, `Intent`, `ValidationResult`, `ElementSignature`, `ElementMeta`, `StrategyTrace`, `Recovered`, `BuildInput`, `CandidateSpec`
- `xpath_healer/core/config.py`
  - `HealerConfig.from_env()`
- `xpath_healer/core/context.py`
  - `StrategyContext.resolve_hints()`
- `xpath_healer/core/strategy_registry.py`
  - `register()`, `evaluate_all()`
- `xpath_healer/core/builder.py`
  - `build_all_candidates()`
- `xpath_healer/core/validator.py`
  - `validate_candidate()`
- `xpath_healer/core/signature.py`
  - `capture()`, `build_robust_locator()`, `build_robust_xpath()`
- `xpath_healer/core/healing_service.py`
  - `recover_locator()` and persistence/scoring helpers
- `xpath_healer/api/facade.py`
  - high-level API/wiring

## 4) Core Code Graph

```text
XPathHealerFacade.recover_locator
 -> HealingService.recover_locator
    -> _evaluate_candidates (per stage)
    -> validator.validate_candidate
    -> signature.capture/build_robust_*
    -> repository.upsert/log_event
```

## 5) Cascade Order (Must Match)
1. fallback
2. metadata
3. rules
4. signature
5. dom_mining
6. rag(optional)
7. defaults
8. position

## 6) Input/Output Contract
Input:
- `page`, `app_id`, `page_name`, `element_name`, `field_type`, `fallback`, `vars`, optional `hints`

Output (`Recovered`):
- `status`: success/failed
- `correlation_id`
- `locator_spec` (on success)
- `strategy_id`
- `trace` (always)
- `metadata` (on success)
- `error` (on fail)

## 7) Exact Implementation Prompt (Core)
```text
Implement Layer 1 (core) for xpath-healer using existing contract names.
Requirements:
1) Implement all domain dataclasses in core/models.py with JSON serialization helpers.
2) Implement LocatorSpec.to_playwright_locator for css/xpath/role/text/pw.
3) Implement deterministic HealingService cascade in exact order:
   fallback -> metadata -> rules -> signature -> dom_mining -> rag(optional) -> defaults -> position.
4) Every candidate must pass XPathValidator.validate_candidate.
5) Capture StrategyTrace entries for each attempt and include stage summary failures.
6) On success, persist ElementMeta with locator_variants and quality_metrics.
7) Keep async API surface and method names unchanged.
8) Add unit tests for validator, models serialization, registry ordering, healing service pass/fail cases.
Output file-by-file with runnable code.
```

## 8) Acceptance Criteria
- Unit tests pass for core modules.
- Recovered trace includes fallback fail + later stage success on broken locator.
- Metadata contains `last_good`, `robust_xpath`, `robust_css`, `live_xpath`, `live_css` variants.
- Quality metrics present with uniqueness/stability/similarity/overall.

## 9) Prior Setup Needed
- Python and venv
- `python -m pip install playwright pytest pytest-asyncio pytest-bdd`
- `python -m playwright install chromium`
