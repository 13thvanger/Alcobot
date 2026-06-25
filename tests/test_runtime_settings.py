import pytest

from app.runtime_settings import get_all_settings, validate_setting


class FakeRow:
    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value


class FakeSession:
    async def execute(self, _query):
        return [
            FakeRow("timezone", "Europe/Moscow"),
            FakeRow("llm_max_tokens", "4000"),
        ]


async def test_get_all_settings_converts_result_rows() -> None:
    values = await get_all_settings(FakeSession())  # type: ignore[arg-type]
    assert values == {
        "timezone": "Europe/Moscow",
        "llm_max_tokens": "4000",
    }


def test_validate_regular_settings() -> None:
    assert validate_setting("timezone", "Europe/Moscow", {"beer"}) == "Europe/Moscow"
    assert validate_setting("llm_temperature", "0,5", {"beer"}) == "0.5"
    assert validate_setting("llm_max_tokens", "4000", {"beer"}) == "4000"


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
