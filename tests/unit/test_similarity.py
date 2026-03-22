from xpath_healer.core.models import ElementSignature
from xpath_healer.core.similarity import SimilarityService


def test_similarity_prefers_stable_attributes() -> None:
    service = SimilarityService(threshold=0.72)
    baseline = ElementSignature(
        tag="input",
        stable_attrs={"data-testid": "username-input", "name": "username"},
        short_text="",
        container_path=["role:form", "testid:login-card"],
    )
    close = ElementSignature(
        tag="input",
        stable_attrs={"data-testid": "username-input", "name": "username"},
        short_text="",
        container_path=["role:form", "testid:login-card"],
    )
    far = ElementSignature(
        tag="div",
        stable_attrs={"data-testid": "e7f93ab9", "name": "id-12839123"},
        short_text="random",
        container_path=["role:grid"],
    )

    close_score = service.score(baseline, close)
    far_score = service.score(baseline, far)

    assert close_score.score > far_score.score
    assert close_score.score >= 0.9
    assert far_score.score < 0.7

