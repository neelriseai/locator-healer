import pytest

from tests.unit.fakes import FakeElement, FakePage
from xpath_healer.api.facade import XPathHealerFacade
from xpath_healer.core.config import HealerConfig
from xpath_healer.core.models import LocatorSpec


class _ScriptedRagAssist:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def suggest(self, inp, html: str, top_k: int = 5, deep_graph: bool | None = None):  # noqa: ANN001
        _ = inp, html, top_k
        self.calls.append(bool(deep_graph))
        if len(self.calls) == 1:
            return [
                LocatorSpec(
                    kind="css",
                    value="div",
                    options={
                        "_llm_confidence": 0.22,
                        "_llm_reason": "guess",
                        "_llm_needs_more_context": True,
                    },
                )
            ]
        return [
            LocatorSpec(
                kind="css",
                value='[name="email"]',
                options={
                    "_llm_confidence": 0.93,
                    "_llm_reason": "unique name attribute",
                },
            )
        ]


def _llm_only_rag_config() -> HealerConfig:
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
    return cfg


@pytest.mark.asyncio
async def test_rag_deep_retry_runs_after_low_confidence_and_failed_validation() -> None:
    cfg = _llm_only_rag_config()
    cfg.prompt.graph_deep_default = False
    cfg.prompt.graph_deep_retry_enabled = True
    cfg.prompt.graph_deep_retry_max = 1
    cfg.llm.min_confidence_for_accept = 0.65

    page = FakePage()
    page.add_element(
        FakeElement(tag="input", attrs={"name": "email", "type": "text"}),
        selectors=['[name="email"]', "input"],
    )
    rag = _ScriptedRagAssist()
    facade = XPathHealerFacade(config=cfg, rag_assist=rag)

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
    assert rag.calls == [False, True]
    assert any(
        entry.stage == "rag" and entry.status == "fail" and entry.details.get("rag_pass") == "light"
        for entry in recovered.trace
    )
    assert any(
        entry.stage == "rag" and entry.status == "ok" and entry.details.get("rag_pass") == "deep_1"
        for entry in recovered.trace
    )


@pytest.mark.asyncio
async def test_rag_deep_retry_can_be_disabled() -> None:
    cfg = _llm_only_rag_config()
    cfg.prompt.graph_deep_default = False
    cfg.prompt.graph_deep_retry_enabled = False
    cfg.prompt.graph_deep_retry_max = 1
    cfg.llm.min_confidence_for_accept = 0.65

    page = FakePage()
    page.add_element(
        FakeElement(tag="input", attrs={"name": "email", "type": "text"}),
        selectors=['[name="email"]', "input"],
    )
    rag = _ScriptedRagAssist()
    facade = XPathHealerFacade(config=cfg, rag_assist=rag)

    recovered = await facade.recover_locator(
        page=page,
        app_id="app",
        page_name="login",
        element_name="email_input",
        field_type="textbox",
        fallback=LocatorSpec(kind="xpath", value="//never-match"),
        vars={"label": "Email"},
    )

    assert recovered.status == "failed"
    assert rag.calls == [False]
