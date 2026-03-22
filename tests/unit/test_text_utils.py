from xpath_healer.utils.text import normalize_text, token_subset_match


def test_normalize_text_collapses_spaces_and_casefolds() -> None:
    assert normalize_text("  Submit   Form ") == "submit form"


def test_token_subset_match() -> None:
    assert token_subset_match("save changes", "Click to Save your Changes now")
    assert not token_subset_match("save now", "save later")

