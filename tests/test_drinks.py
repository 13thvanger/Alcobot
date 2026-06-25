from datetime import date
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


def test_all_drinks_follow_standard_volume_groups() -> None:
    expected = {
        "beer": Decimal("500"),
        "cider": Decimal("500"),
        "wine": Decimal("150"),
        "champagne": Decimal("150"),
        "vermouth": Decimal("150"),
        "vodka": Decimal("50"),
        "whiskey": Decimal("50"),
        "rum": Decimal("50"),
        "gin": Decimal("50"),
        "tequila": Decimal("50"),
        "cognac": Decimal("50"),
        "liqueur": Decimal("50"),
        "absinthe": Decimal("50"),
    }
    for drink, expected_volume in expected.items():
        result = calculate_short_add(drink)
        assert result is not None
        assert result.volume_ml == expected_volume


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


def test_manual_arguments_can_be_in_any_order() -> None:
    today = date(2026, 6, 25)
    variants = (
        "beer 500 4% 24 мая",
        "beer 4% 24 мая 500",
        "beer 24 мая 500 4%",
        "beer 24 мая 4% 500",
    )
    for text in variants:
        result = calculate_short_add(text, current_date=today)
        assert result is not None
        assert result.volume_ml == Decimal("500")
        assert result.pure_alcohol_ml == Decimal("20.00")
        assert result.consumed_on == date(2026, 5, 24)


def test_manual_numeric_and_iso_dates() -> None:
    today = date(2026, 6, 25)
    dotted = calculate_short_add("wine 12% 750 24.05.2026", current_date=today)
    iso = calculate_short_add("wine 2026-05-24 750 12%", current_date=today)

    assert dotted is not None and dotted.consumed_on == date(2026, 5, 24)
    assert iso is not None and iso.consumed_on == date(2026, 5, 24)
    assert dotted.pure_alcohol_ml == Decimal("90.00")
    assert iso.pure_alcohol_ml == Decimal("90.00")


def test_manual_date_without_year_uses_closest_past_date() -> None:
    result = calculate_short_add(
        "beer 31 декабря 500 5%",
        current_date=date(2026, 6, 25),
    )
    assert result is not None
    assert result.consumed_on == date(2025, 12, 31)


def test_manual_date_with_default_volume() -> None:
    result = calculate_short_add("wine 12% 24 мая", current_date=date(2026, 6, 25))
    assert result is not None
    assert result.volume_ml == Decimal("150")
    assert result.consumed_on == date(2026, 5, 24)


def test_duplicate_or_future_manual_date_falls_back_to_llm() -> None:
    today = date(2026, 6, 25)
    assert calculate_short_add("beer 24 мая 25 мая", current_date=today) is None
    assert calculate_short_add("beer 2026-06-26", current_date=today) is None


def test_standard_serving_words_use_drink_group_volume() -> None:
    beer = calculate_short_add("beer бокал")
    wine = calculate_short_add("wine бокал")
    vodka_shot = calculate_short_add("vodka шот")
    vodka_stack = calculate_short_add("vodka стопка")

    assert beer is not None and beer.volume_ml == Decimal("500")
    assert wine is not None and wine.volume_ml == Decimal("150")
    assert vodka_shot is not None and vodka_shot.volume_ml == Decimal("50")
    assert vodka_stack is not None and vodka_stack.volume_ml == Decimal("50")


def test_explicit_volume_overrides_serving_word() -> None:
    result = calculate_short_add("beer бокал 400 4%")
    assert result is not None
    assert result.volume_ml == Decimal("400")
    assert result.pure_alcohol_ml == Decimal("16.00")
