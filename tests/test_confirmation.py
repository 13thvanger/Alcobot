from decimal import Decimal

from app.handlers import confirmation_keyboard, format_calculation_items


def test_confirmation_keyboard_contains_token() -> None:
    keyboard = confirmation_keyboard("abc123")
    buttons = keyboard.inline_keyboard[0]
    assert buttons[0].callback_data == "add_confirm:abc123"
    assert buttons[1].callback_data == "add_cancel:abc123"


def test_format_calculation_items() -> None:
    text = format_calculation_items(
        {
            "items": [
                {
                    "name": "пиво",
                    "volume_ml": 500,
                    "abv_percent": 5,
                    "pure_alcohol_ml": Decimal("25"),
                }
            ]
        },
        "beer 500",
    )
    assert "пиво" in text
    assert "500 мл" in text
    assert "25 мл спирта" in text


def test_format_calculation_items_escapes_text() -> None:
    text = format_calculation_items({"items": []}, "<beer>")
    assert text == "• &lt;beer&gt;"
