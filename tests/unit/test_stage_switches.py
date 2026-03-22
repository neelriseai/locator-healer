import pytest

from tests.unit.fakes import FakeElement, FakePage
from xpath_healer.api.facade import XPathHealerFacade
from xpath_healer.core.config import HealerConfig
from xpath_healer.core.models import LocatorSpec


class StubRagAssist:
    async def suggest(self, inp, html: str, top_k: int = 5):  # noqa: ANN001
        _ = inp
        _ = html
        _ = top_k
        return [LocatorSpec(kind="css", value='[name="email"]')]


def test_stage_profile_llm_only(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("XH_TEST_STAGE_PROFILE", "llm_only")
    cfg = HealerConfig.from_env(prefix="XH_TEST_")
    assert cfg.stages.profile == "llm_only"
    assert cfg.stages.fallback is False
    assert cfg.stages.metadata is False
    assert cfg.stages.rules is False
    assert cfg.stages.fingerprint is False
    assert cfg.stages.page_index is False
    assert cfg.stages.signature is False
    assert cfg.stages.dom_mining is False
    assert cfg.stages.defaults is False
    assert cfg.stages.position is False
    assert cfg.stages.rag is True


@pytest.mark.asyncio
async def test_recover_with_only_rag_stage_enabled() -> None:
    cfg = HealerConfig()
    cfg.rag.enabled = True
    cfg.stages.fallback = False
    cfg.stages.metadata = False
    cfg.stages.rules = False
    cfg.stages.fingerprint = False
    cfg.stages.page_index = False
    cfg.stages.signature = False
    cfg.stages.dom_mining = False
    cfg.stages.defaults = False
    cfg.stages.position = False
    cfg.stages.rag = True

    page = FakePage()
    page.add_element(
        FakeElement(tag="input", attrs={"name": "email", "type": "text"}),
        selectors=['[name="email"]', "input"],
    )
    facade = XPathHealerFacade(config=cfg, rag_assist=StubRagAssist())
    recovered = await facade.recover_locator(
        page=page,
        app_id="app",
        page_name="login",
        element_name="email_input",
        field_type="textbox",
        fallback=LocatorSpec(kind="xpath", value="//never-match"),
        vars={"label": "Email"},
    )

    assert recovered.status == "success"
    assert recovered.strategy_id == "rag_suggest"
    assert recovered.locator_spec is not None
    assert recovered.locator_spec.kind == "css"
    assert recovered.locator_spec.value == '[name="email"]'
    assert not any(entry.stage == "fallback" for entry in recovered.trace)
