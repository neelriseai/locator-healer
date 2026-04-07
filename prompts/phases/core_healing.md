Title: Phase Prompt - Core Healing Layer

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Build and harden deterministic healing behavior in `xpath_healer/core` and facade orchestration.

Prompt to use with AI assistant:

```
Implement Core Healing Layer.

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
- xpath_healer/api/base.py

Required behavior:
1. Preserve exact stage order:
   fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag
2. Respect stage flags via `HealerConfig.from_env`.
3. Keep stage pipeline sequential.
4. Keep candidate validation parallel only in designated stages via `_evaluate_candidates_parallel`.
5. Keep candidate validation sequential where `_evaluate_candidates` is used.
6. Emit structured trace and stage events.
7. Maintain retry logic (`XH_RETRY_*`) for transient reason codes.
8. Persist success/failure through repository interface (no backend-specific logic in core).

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
- `HealingService.recover_locator` follows sequence and honors flags.
- Recovery returns `Recovered` with trace entries and correlation id.
- Validator blocks invalid/multi-match candidates when strict mode applies.
- Existing integration flow remains compatible.

Validation commands:
- `python -m pytest -q tests/unit/test_healing_service.py`
- `python -m pytest -q tests/unit/test_stage_switches.py`
- `python -m pytest -q tests/unit/test_validator.py`
