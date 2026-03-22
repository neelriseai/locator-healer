from types import SimpleNamespace

import pytest

from xpath_healer.core.builder import XPathBuilder
from xpath_healer.core.config import HealerConfig
from xpath_healer.core.healing_service import HealingService
from xpath_healer.core.models import BuildInput, CandidateSpec, Intent, LocatorSpec, ValidationResult
from xpath_healer.core.strategy_registry import StrategyRegistry


class _ScriptedValidator:
    def __init__(self, responses: list[ValidationResult]) -> None:
        self.responses = responses
        self.calls = 0
        self.strict_args: list[bool | None] = []

    async def validate_candidate(self, page, locator, field_type, intent, strict_single_match=None):  # type: ignore[no-untyped-def]
        _ = page, locator, field_type, intent, strict_single_match
        self.strict_args.append(strict_single_match)
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


def _build_input() -> BuildInput:
    return BuildInput(
        page=None,
        app_id="app",
        page_name="page",
        element_name="element",
        field_type="textbox",
        fallback=LocatorSpec(kind="xpath", value="//broken"),
        vars={},
        intent=Intent.from_vars({}),
    )


@pytest.mark.asyncio
async def test_retry_happens_for_transient_reason_code() -> None:
    service = HealingService(builder=XPathBuilder(StrategyRegistry([])))
    config = HealerConfig()
    config.retry.enabled = True
    config.retry.max_attempts = 2
    config.retry.delay_ms = 0
    config.retry.retry_reason_codes = ["locator_error"]

    validator = _ScriptedValidator(
        [
            ValidationResult.fail(["locator_error"]),
            ValidationResult.success(matched_count=1, chosen_index=0),
        ]
    )
    ctx = SimpleNamespace(config=config, validator=validator)
    inp = _build_input()
    candidate = CandidateSpec(strategy_id="test", locator=LocatorSpec(kind="css", value="input"), stage="rules")

    validation, attempts = await service._validate_candidate_with_retry(ctx, inp, candidate)
    assert validation.ok
    assert attempts == 2
    assert validator.calls == 2


@pytest.mark.asyncio
async def test_retry_skipped_for_non_transient_reason_code() -> None:
    service = HealingService(builder=XPathBuilder(StrategyRegistry([])))
    config = HealerConfig()
    config.retry.enabled = True
    config.retry.max_attempts = 3
    config.retry.delay_ms = 0
    config.retry.retry_reason_codes = ["locator_error"]

    validator = _ScriptedValidator(
        [
            ValidationResult.fail(["no_match"]),
            ValidationResult.success(matched_count=1, chosen_index=0),
        ]
    )
    ctx = SimpleNamespace(config=config, validator=validator)
    inp = _build_input()
    candidate = CandidateSpec(strategy_id="test", locator=LocatorSpec(kind="css", value="input"), stage="rules")

    validation, attempts = await service._validate_candidate_with_retry(ctx, inp, candidate)
    assert not validation.ok
    assert attempts == 1
    assert validator.calls == 1


@pytest.mark.asyncio
async def test_intent_strictness_overrides_default_hints_setting() -> None:
    service = HealingService(builder=XPathBuilder(StrategyRegistry([])))
    config = HealerConfig()
    config.retry.enabled = False

    validator = _ScriptedValidator([ValidationResult.success(matched_count=2, chosen_index=0)])
    ctx = SimpleNamespace(config=config, validator=validator)
    inp = _build_input()
    inp.hints = SimpleNamespace(strict_single_match=True)
    inp.intent.strict_single_match = False
    candidate = CandidateSpec(strategy_id="test", locator=LocatorSpec(kind="css", value="input"), stage="rules")

    validation, attempts = await service._validate_candidate_with_retry(ctx, inp, candidate)

    assert validation.ok
    assert attempts == 1
    assert validator.strict_args == [False]


def test_resolve_selected_locator_adds_nth_for_multi_match() -> None:
    service = HealingService(builder=XPathBuilder(StrategyRegistry([])))
    locator = LocatorSpec(kind="css", value="input")
    validation = ValidationResult.success(matched_count=3, chosen_index=1)

    resolved = service._resolve_selected_locator(locator, validation)

    assert resolved.options.get("nth") == 1
    assert resolved.kind == "css"
    assert resolved.value == "input"
