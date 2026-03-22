import pytest

from tests.unit.fakes import FakeElement, FakePage
from xpath_healer.api.facade import XPathHealerFacade
from xpath_healer.core.config import HealerConfig
from xpath_healer.core.models import BuildInput, Intent, LocatorSpec
from xpath_healer.core.page_index import PageIndexer
from xpath_healer.store.memory_repository import InMemoryMetadataRepository


def test_page_indexer_ranks_submit_order_candidate_first() -> None:
    html = """
    <html>
      <body>
        <div class="checkout">
          <button id="submit-order-new" role="button">Submit Order</button>
          <button id="place-order" role="button">Place Order</button>
          <button role="button">Submit</button>
        </div>
      </body>
    </html>
    """
    indexer = PageIndexer(top_k=5)
    page_index = indexer.build_page_index("shop-app", "checkout", html)
    inp = BuildInput(
        page=None,
        app_id="shop-app",
        page_name="checkout",
        element_name="submit_order_button",
        field_type="button",
        fallback=LocatorSpec(kind="xpath", value="//missing"),
        vars={"label": "Submit Order", "text": "Submit Order"},
        intent=Intent.from_vars({"label": "Submit Order", "text": "Submit Order"}),
    )

    ranked = indexer.rank_candidates(page_index, inp, meta=None)

    assert ranked
    assert ranked[0].score >= ranked[-1].score
    assert "submit-order-new" in ranked[0].locator.value


@pytest.mark.asyncio
async def test_recover_uses_page_index_stage_when_enabled() -> None:
    cfg = HealerConfig()
    cfg.stages.fallback = False
    cfg.stages.metadata = False
    cfg.stages.rules = False
    cfg.stages.fingerprint = False
    cfg.stages.page_index = True
    cfg.stages.signature = False
    cfg.stages.dom_mining = False
    cfg.stages.defaults = False
    cfg.stages.position = False
    cfg.stages.rag = False

    page = FakePage()
    submit_order = FakeElement(tag="button", text="Submit Order", attrs={"id": "submit-order-new", "role": "button"})
    place_order = FakeElement(tag="button", text="Place Order", attrs={"id": "place-order", "role": "button"})
    submit_generic = FakeElement(tag="button", text="Submit", attrs={"role": "button"})
    page.add_element(submit_order, selectors=['[id="submit-order-new"]', "button"])
    page.add_element(place_order, selectors=['[id="place-order"]', "button"])
    page.add_element(submit_generic, selectors=["button"])

    facade = XPathHealerFacade(config=cfg, repository=InMemoryMetadataRepository())
    recovered = await facade.recover_locator(
        page=page,
        app_id="shop-app",
        page_name="checkout",
        element_name="submit_order_button",
        field_type="button",
        fallback=LocatorSpec(kind="xpath", value="//never-match"),
        vars={"label": "Submit Order", "text": "Submit Order"},
    )

    assert recovered.status == "success"
    assert recovered.strategy_id is not None
    assert recovered.strategy_id.startswith("page_index.rank:")
    assert recovered.locator_spec is not None
    assert "submit-order-new" in recovered.locator_spec.value
    assert any(entry.stage == "page_index" and entry.status == "ok" for entry in recovered.trace)
