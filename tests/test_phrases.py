from app.phrases import load_phrases, random_phrase


def test_phrase_file_contains_required_sections() -> None:
    phrases = load_phrases()
    assert phrases["add"]
    assert phrases["stat"]


def test_random_phrase_uses_requested_section() -> None:
    phrases = load_phrases()
    assert random_phrase("add") in phrases["add"]
    assert random_phrase("stat") in phrases["stat"]


def test_unknown_section_is_empty() -> None:
    assert random_phrase("unknown") == ""

