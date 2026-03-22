from xpath_healer.core.models import BuildInput, Intent, LocatorSpec
from xpath_healer.rag.prompt_builder import build_prompt_payload, extract_dom_context
from xpath_healer.rag.prompt_dsl import build_prompt_dsl


def test_prompt_dsl_uses_compact_sections() -> None:
    inp = BuildInput(
        page=None,
        app_id="app",
        page_name="checkout",
        element_name="submit_button",
        field_type="button",
        fallback=LocatorSpec(kind="xpath", value="//button[@id='broken-submit']"),
        vars={"label": "Submit Order", "name": "submit-order"},
        intent=Intent.from_vars({"label": "Submit Order", "text": "Submit Order"}),
    )
    dsl = build_prompt_dsl(
        inp,
        "<html><body><form class='checkout'><button id='submit-order'>Submit Order</button></form></body></html>",
        [{"locator": {"kind": "css", "value": "#submit-order", "options": {}}, "rerank_score": 0.97}],
        [{"tag": "button", "role": "button", "label": "Submit Order", "text": "Submit Order", "attrs": {"id": "submit-order"}}],
    )

    assert "E submit_button" in dsl
    assert "PG checkout" in dsl
    assert "FT button" in dsl
    assert "F xpath=//button[@id='broken-submit']" in dsl
    assert "A " in dsl
    assert "C" in dsl
    assert "H" in dsl
    assert "D " in dsl
    assert "O JSON only:" in dsl
    assert "Schema" not in dsl


def test_prompt_payload_exposes_compact_dom_signature_and_output_schema() -> None:
    inp = BuildInput(
        page=None,
        app_id="app",
        page_name="checkout",
        element_name="submit_button",
        field_type="button",
        fallback=LocatorSpec(kind="xpath", value="//button[@id='broken-submit']"),
        vars={},
        intent=Intent.from_vars({"text": "Submit"}),
    )
    payload = build_prompt_payload(
        inp=inp,
        dom_snippet="<html><body><button>Submit</button><button>Cancel</button></body></html>",
        context_candidates=[],
    )

    assert "dom_signature" in payload
    assert "dom_snippet" not in payload
    assert "intent" not in payload
    assert "vars" not in payload
    output_schema = payload["rules"]["output_schema"]
    assert "confidence" in output_schema
    assert "reason" in output_schema
    assert "needs_more_context" in output_schema
    assert payload["mode"] == "default"


def test_extract_dom_context_reads_controls_beyond_initial_html_prefix() -> None:
    prefix = "<div>" + ("x" * 25000) + "</div>"
    html = (
        "<html><body>"
        + prefix
        + '<label for="userName">Full Name</label>'
        + '<input id="userName" name="userName" placeholder="Full Name" type="text">'
        + '<textarea id="currentAddress" placeholder="Current Address"></textarea>'
        + "</body></html>"
    )

    context = extract_dom_context(html, deep_graph=True)

    assert any(
        item["tag"] == "input" and item["attrs"].get("id") == "userName" and item["label"] == "Full Name"
        for item in context
    )
    assert any(
        item["tag"] == "textarea" and item["attrs"].get("id") == "currentAddress" and item["label"] == "Current Address"
        for item in context
    )


def test_extract_dom_context_preserves_visible_text_case_and_label_proxy_type() -> None:
    html = (
        '<html><body><label for="tree-node-home"><input id="tree-node-home" type="checkbox">'
        '<span class="rct-checkbox"></span><span class="rct-title">Home</span></label>'
        '<div role="gridcell">Vega</div></body></html>'
    )

    context = extract_dom_context(html, deep_graph=True)

    assert any(item["tag"] == "label" and item.get("role") == "checkbox" and item.get("control_type") == "checkbox" for item in context)
    assert any(item["tag"] == "div" and item.get("text") == "Vega" for item in context)
