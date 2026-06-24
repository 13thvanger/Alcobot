import pytest

from app.runtime_settings import validate_setting


def test_validate_regular_settings() -> None:
    assert validate_setting("timezone", "Europe/Moscow", {"beer"}) == "Europe/Moscow"
    assert validate_setting("llm_temperature", "0,5", {"beer"}) == "0.5"
    assert validate_setting("llm_max_tokens", "2000", {"beer"}) == "2000"


def test_validate_drink_settings() -> None:
    assert validate_setting("drink.beer.abv", "4.7", {"beer"}) == "4.7"
    assert validate_setting("drink.beer.volume", "450", {"beer"}) == "450"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("timezone", "Nowhere/Unknown"),
        ("llm_temperature", "3"),
        ("llm_max_tokens", "10"),
        ("drink.unknown.abv", "5"),
        ("drink.beer.abv", "101"),
    ],
)
def test_reject_invalid_settings(key: str, value: str) -> None:
    with pytest.raises(ValueError):
        validate_setting(key, value, {"beer"})
