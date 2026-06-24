import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Drink:
    key: str
    title: str
    abv_percent: Decimal
    default_volume_ml: Decimal
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class DrinkCalculation:
    drink: Drink | None
    volume_ml: Decimal
    pure_alcohol_ml: Decimal

    @property
    def summary(self) -> str:
        if self.drink is None:
            return f"{self.volume_ml:g} мл чистого спирта"
        return (
            f"{self.drink.title}: {self.volume_ml:g} мл × "
            f"{self.drink.abv_percent:g}% = {self.pure_alcohol_ml:g} мл спирта"
        )

    def as_result(self) -> dict:
        if self.drink is None:
            return {
                "pure_alcohol_ml": float(self.pure_alcohol_ml),
                "items": [
                    {
                        "name": "чистый спирт",
                        "volume_ml": float(self.volume_ml),
                        "abv_percent": 100,
                        "pure_alcohol_ml": float(self.pure_alcohol_ml),
                    }
                ],
                "summary": self.summary,
                "calculation_source": "drink_table",
            }
        return {
            "pure_alcohol_ml": float(self.pure_alcohol_ml),
            "items": [
                {
                    "name": self.drink.key,
                    "volume_ml": float(self.volume_ml),
                    "abv_percent": float(self.drink.abv_percent),
                    "pure_alcohol_ml": float(self.pure_alcohol_ml),
                }
            ],
            "summary": self.summary,
            "calculation_source": "drink_table",
        }


DRINKS = (
    Drink("beer", "Пиво", Decimal("5"), Decimal("500"), ("beer", "пиво")),
    Drink(
        "cider",
        "Сидр",
        Decimal("5"),
        Decimal("500"),
        ("cider", "сидр"),
    ),
    Drink(
        "wine",
        "Вино",
        Decimal("12"),
        Decimal("150"),
        ("wine", "вино"),
    ),
    Drink(
        "champagne",
        "Игристое вино",
        Decimal("12"),
        Decimal("150"),
        ("champagne", "sparkling", "шампанское", "игристое"),
    ),
    Drink(
        "vermouth",
        "Вермут",
        Decimal("16"),
        Decimal("150"),
        ("vermouth", "вермут", "martini", "мартини"),
    ),
    Drink("vodka", "Водка", Decimal("40"), Decimal("50"), ("vodka", "водка")),
    Drink(
        "whiskey",
        "Виски",
        Decimal("40"),
        Decimal("50"),
        ("whiskey", "whisky", "виски"),
    ),
    Drink("rum", "Ром", Decimal("40"), Decimal("50"), ("rum", "ром")),
    Drink("gin", "Джин", Decimal("40"), Decimal("50"), ("gin", "джин")),
    Drink(
        "tequila",
        "Текила",
        Decimal("40"),
        Decimal("50"),
        ("tequila", "текила"),
    ),
    Drink(
        "cognac",
        "Коньяк",
        Decimal("40"),
        Decimal("50"),
        ("cognac", "brandy", "коньяк", "бренди"),
    ),
    Drink(
        "liqueur",
        "Ликёр",
        Decimal("25"),
        Decimal("50"),
        ("liqueur", "liquor", "ликер", "ликёр"),
    ),
    Drink(
        "absinthe",
        "Абсент",
        Decimal("70"),
        Decimal("50"),
        ("absinthe", "абсент"),
    ),
)

DRINK_BY_ALIAS = {alias: drink for drink in DRINKS for alias in drink.aliases}
DRINK_KEYS = {drink.key for drink in DRINKS}
VOLUME_PATTERN = re.compile(r"^(?P<amount>\d+(?:[.,]\d+)?)\s*(?:ml|мл)?$", re.IGNORECASE)


def _parse_volume(value: str) -> Decimal | None:
    match = VOLUME_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    try:
        volume = Decimal(match.group("amount").replace(",", "."))
    except InvalidOperation:
        return None
    if volume <= 0 or volume > Decimal("10000"):
        return None
    return volume


def calculate_short_add(
    text: str, overrides: dict[str, dict[str, Decimal]] | None = None
) -> DrinkCalculation | None:
    """Parse `/add [drink] [millilitres]`; return None for free-form LLM input."""
    parts = text.lower().strip().split()
    if not parts or len(parts) > 2:
        return None

    if len(parts) == 1:
        volume = _parse_volume(parts[0])
        if volume is not None:
            return DrinkCalculation(None, volume, volume)
        drink = DRINK_BY_ALIAS.get(parts[0])
        if drink is None:
            return None
        volume = drink.default_volume_ml
    else:
        drink = DRINK_BY_ALIAS.get(parts[0])
        if drink is None:
            return None
        volume = _parse_volume(parts[1])
        if volume is None:
            return None

    override = (overrides or {}).get(drink.key, {})
    if len(parts) == 1:
        volume = override.get("volume", volume)
    abv = override.get("abv", drink.abv_percent)
    effective_drink = Drink(
        drink.key,
        drink.title,
        abv,
        override.get("volume", drink.default_volume_ml),
        drink.aliases,
    )
    pure_alcohol_ml = (volume * abv / 100).quantize(Decimal("0.01"))
    return DrinkCalculation(effective_drink, volume, pure_alcohol_ml)
