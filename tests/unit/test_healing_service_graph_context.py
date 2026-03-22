from xpath_healer.core.builder import XPathBuilder
from xpath_healer.core.healing_service import HealingService
from xpath_healer.core.models import BuildInput, ElementSignature, Intent, LocatorSpec
from xpath_healer.core.strategy_registry import StrategyRegistry


def test_graph_context_score_prefers_structural_and_anchor_match() -> None:
    service = HealingService(builder=XPathBuilder(StrategyRegistry([])))
    inp = BuildInput(
        page=None,
        app_id="app",
        page_name="login",
        element_name="email",
        field_type="textbox",
        fallback=LocatorSpec(kind="css", value="*"),
        vars={"label": "Email", "text": "Email"},
        intent=Intent.from_vars({"label": "Email", "text": "Email"}),
    )

    target = ElementSignature(
        tag="input",
        stable_attrs={},
        short_text="",
        container_path=["role:form", "testid:login-card"],
    )
    candidate_good = ElementSignature(
        tag="input",
        stable_attrs={},
        short_text="Email",
        container_path=["role:form", "testid:login-card"],
    )
    candidate_bad = ElementSignature(
        tag="div",
        stable_attrs={},
        short_text="Random",
        container_path=["role:grid"],
    )

    good_score = service._graph_context_score(
        inp=inp,
        target_signature=target,
        candidate_signature=candidate_good,
        neighbor_field_type="textbox",
        neighbor_element_name="email_input",
    )
    bad_score = service._graph_context_score(
        inp=inp,
        target_signature=target,
        candidate_signature=candidate_bad,
        neighbor_field_type="button",
        neighbor_element_name="random_action",
    )

    assert good_score > bad_score
    assert good_score >= 0.70
    assert bad_score <= 0.45
