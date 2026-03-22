Title: Phase Prompt - Core Healing Layer

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Build and harden deterministic healing engine behavior in `xpath_healer/core` and facade orchestration.

Prompt to use with AI assistant:

```
Implement Core Healing Layer aligned to `prompts/01_Master_Design_for_xpath_healer.md`.

Scope:
- xpath_healer/core/config.py
- xpath_healer/core/models.py
- xpath_healer/core/healing_service.py
- xpath_healer/core/builder.py
- xpath_healer/core/strategy_registry.py
- xpath_healer/core/validator.py
- xpath_healer/core/signature.py
- xpath_healer/core/fingerprint.py
- xpath_healer/core/similarity.py
- xpath_healer/core/page_index.py
- xpath_healer/core/strategies/*
- xpath_healer/api/facade.py

Required behavior:
1. Keep stage order:
   fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag.
2. Respect stage flags via `HealerConfig.from_env`.
3. Evaluate candidates with validator gating before accept.
4. Emit structured trace and stage events.
5. Maintain retry logic (`XH_RETRY_*`) for transient reason codes.
6. Persist success/failure through repository interface (no backend-specific logic in core).

Deliverables:
- Code changes with clear method boundaries.
- Any new strategy class under `core/strategies`.
- Unit tests for changed logic.
- Notes on behavior impact and compatibility.

Constraints:
- Do not hardcode secrets.
- Do not add network dependencies in deterministic stages.
- Do not rename existing stage names.
```

Acceptance criteria:
- `HealingService.recover_locator` follows stage sequence and honors flags.
- Recovery returns `Recovered` with trace entries and correlation id.
- Validator must block invalid/multi-match candidates when strict mode applies.
- Existing integration flow remains compatible.

Validation commands:
- `python -m pytest -q tests/unit/test_healing_service.py`
- `python -m pytest -q tests/unit/test_stage_switches.py`
- `python -m pytest -q tests/unit/test_validator.py`

