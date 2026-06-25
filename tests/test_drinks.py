from decimal import Decimal

from app.drinks import calculate_short_add


def test_beer_with_volume() -> None:
    result = calculate_short_add("beer 500")
    assert result is not None
    assert result.pure_alcohol_ml == Decimal("25.00")


def test_drink_uses_default_volume() -> None:
    beer = calculate_short_add("пиво")
    wine = calculate_short_add("wine")
    tequila = calculate_short_add("tequila")

    assert beer is not None and beer.volume_ml == Decimal("500")
    assert wine is not None and wine.volume_ml == Decimal("150")
    assert tequila is not None and tequila.volume_ml == Decimal("50")


def test_number_without_drink_is_pure_alcohol() -> None:
    result = calculate_short_add("40")
    assert result is not None
    assert result.drink is None
    assert result.pure_alcohol_ml == Decimal("40")


def test_accepts_units_and_decimal_comma() -> None:
    result = calculate_short_add("wine 187,5мл")
    assert result is not None
    assert result.pure_alcohol_ml == Decimal("22.50")


def test_free_text_falls_back_to_llm() -> None:
    assert calculate_short_add("два бокала красного вина") is None
    assert calculate_short_add("unknown 500") is None


def test_runtime_drink_overrides() -> None:
    result = calculate_short_add(
        "beer",
        {"beer": {"abv": Decimal("4"), "volume": Decimal("400")}},
    )
    assert result is not None
    assert result.volume_ml == Decimal("400")
    assert result.pure_alcohol_ml == Decimal("16.00")


def test_explicit_abv_with_volume() -> None:
    result = calculate_short_add("beer 500 4%")
    assert result is not None
    assert result.volume_ml == Decimal("500")
    assert result.drink is not None
    assert result.drink.abv_percent == Decimal("4")
    assert result.pure_alcohol_ml == Decimal("20.00")


def test_explicit_abv_uses_default_volume() -> None:
    result = calculate_short_add("wine 12,5%")
    assert result is not None
    assert result.volume_ml == Decimal("150")
    assert result.pure_alcohol_ml == Decimal("18.75")


def test_explicit_abv_overrides_runtime_table() -> None:
    result = calculate_short_add(
        "beer 500 4%",
        {"beer": {"abv": Decimal("8")}},
    )
    assert result is not None
    assert result.pure_alcohol_ml == Decimal("20.00")


def test_invalid_abv_falls_back_to_llm() -> None:
    assert calculate_short_add("beer 500 0%") is None
    assert calculate_short_add("beer 500 101%") is None
