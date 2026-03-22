from xpath_healer.core.fingerprint import FingerprintService
from xpath_healer.core.models import ElementSignature, Intent


def test_fingerprint_build_contains_normalized_tokens_and_hash() -> None:
    service = FingerprintService()
    signature = ElementSignature(
        tag="INPUT",
        stable_attrs={"type": "text", "role": "textbox", "placeholder": "Email Address"},
        short_text="",
        container_path=["role:form", "testid:login-card"],
    )
    intent = Intent.from_vars({"label": "Email"})

    fp = service.build(signature, field_type="textbox", intent=intent, element_name="email_input")

    assert fp.hash_value
    assert fp.tokens["tag"] == "input"
    assert fp.tokens["type"] == "text"
    assert fp.tokens["label"] == "email"
    assert "container" in fp.tokens


def test_fingerprint_compare_returns_exact_hash_match() -> None:
    service = FingerprintService()
    signature = ElementSignature(
        tag="input",
        stable_attrs={"type": "text", "role": "textbox"},
        short_text="Email",
        container_path=["role:form"],
    )
    fp_a = service.build(signature, field_type="textbox", element_name="email")
    fp_b = service.build(signature, field_type="textbox", element_name="email")

    match = service.compare(fp_a, fp_b)

    assert match.exact_hash is True
    assert match.score == 0.98


def test_fingerprint_weighted_scoring_prefers_structural_neighbor() -> None:
    service = FingerprintService()
    expected = service.build(
        ElementSignature(
            tag="input",
            stable_attrs={"type": "text", "role": "textbox"},
            short_text="Email",
            container_path=["role:form", "testid:login-card"],
        ),
        field_type="textbox",
        intent=Intent.from_vars({"label": "Email"}),
        element_name="email_input",
    )

    close = service.build(
        ElementSignature(
            tag="input",
            stable_attrs={"type": "text", "role": "textbox"},
            short_text="Email address",
            container_path=["role:form", "testid:login-card"],
        ),
        field_type="textbox",
        element_name="email_field",
    )
    far = service.build(
        ElementSignature(
            tag="button",
            stable_attrs={"type": "button", "role": "button"},
            short_text="Submit",
            container_path=["role:toolbar"],
        ),
        field_type="button",
        element_name="submit_button",
    )

    close_match = service.compare(expected, close)
    far_match = service.compare(expected, far)

    assert close_match.score > far_match.score
    assert close_match.score >= 0.75
    assert service.confidence_band(close_match.score) in {"medium", "high"}
    assert service.confidence_band(far_match.score) == "low"
