"""Детерминированный калькулятор для короткой формы команды /add."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Drink:
    # @dataclass генерирует __init__, __repr__ и сравнение объектов.
    # frozen=True запрещает менять поля после создания — аналог value object.
    key: str
    title: str
    abv_percent: Decimal
    default_volume_ml: Decimal
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class DrinkCalculation:
    # Union через ``|``: drink либо Drink, либо None (аналог nullable pointer,
    # но None нельзя разыменовать — перед использованием нужна проверка).
    drink: Drink | None
    volume_ml: Decimal
    pure_alcohol_ml: Decimal

    @property
    def summary(self) -> str:
        if self.drink is None:
            return f"{self.volume_ml:g} мл чистого спирта"
        # f-string подставляет выражения из {...}; спецификатор :g компактно
        # форматирует Decimal без лишних конечных нулей.
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


# Кортеж выбран вместо списка, потому что таблица не должна меняться в runtime.
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

# Dict/set comprehensions — компактные циклы создания контейнеров.
# Первая строка эквивалентна двум вложенным for и присваиванию в dict.
DRINK_BY_ALIAS = {alias: drink for drink in DRINKS for alias in drink.aliases}
DRINK_KEYS = {drink.key for drink in DRINKS}
VOLUME_PATTERN = re.compile(r"^(?P<amount>\d+(?:[.,]\d+)?)\s*(?:ml|мл)?$", re.IGNORECASE)
ABV_PATTERN = re.compile(r"^(?P<amount>\d+(?:[.,]\d+)?)\s*%$", re.IGNORECASE)


def _parse_volume(value: str) -> Decimal | None:
    # Начальный ``_`` — соглашение "внутренняя функция модуля", не модификатор
    # private: при желании импортировать её всё равно возможно.
    match = VOLUME_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    try:
        volume = Decimal(match.group("amount").replace(",", "."))
    except InvalidOperation:
        # Исключения работают близко к C++ exceptions. Здесь неверный ввод —
        # ожидаемая ситуация, поэтому превращаем его в None.
        return None
    if volume <= 0 or volume > Decimal("10000"):
        return None
    return volume


def _parse_abv(value: str) -> Decimal | None:
    """Разобрать крепость вида ``4%`` или ``12,5%``."""
    match = ABV_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    try:
        abv = Decimal(match.group("amount").replace(",", "."))
    except InvalidOperation:
        return None
    if abv <= 0 or abv > 100:
        return None
    return abv


def calculate_short_add(
    text: str, overrides: dict[str, dict[str, Decimal]] | None = None
) -> DrinkCalculation | None:
    """Parse `/add [drink] [millilitres] [ABV%]`.

    Для свободного текста возвращается None, после чего обработчик вызывает LLM.
    """
    # Цепочки методов читаются слева направо: lower -> strip -> split.
    parts = text.lower().strip().split()
    if not parts or len(parts) > 3:
        return None

    explicit_abv: Decimal | None = None
    if len(parts) == 1:
        volume = _parse_volume(parts[0])
        if volume is not None:
            return DrinkCalculation(None, volume, volume)
        drink = DRINK_BY_ALIAS.get(parts[0])
        if drink is None:
            return None
        volume = drink.default_volume_ml
    elif len(parts) == 2:
        drink = DRINK_BY_ALIAS.get(parts[0])
        if drink is None:
            return None
        explicit_abv = _parse_abv(parts[1])
        if explicit_abv is not None:
            volume = drink.default_volume_ml
        else:
            volume = _parse_volume(parts[1])
            if volume is None:
                return None
    else:
        drink = DRINK_BY_ALIAS.get(parts[0])
        if drink is None:
            return None
        volume = _parse_volume(parts[1])
        explicit_abv = _parse_abv(parts[2])
        if volume is None or explicit_abv is None:
            return None

    # ``x or {}`` возвращает первый truthy-операнд. None и пустой dict считаются
    # false. get(key, default) не выбрасывает исключение при отсутствии ключа.
    override = (overrides or {}).get(drink.key, {})
    if len(parts) == 1 or (len(parts) == 2 and explicit_abv is not None):
        volume = override.get("volume", volume)
    # Явно написанные пользователем проценты важнее runtime-настроек и таблицы.
    abv = explicit_abv or override.get("abv", drink.abv_percent)
    effective_drink = Drink(
        drink.key,
        drink.title,
        abv,
        override.get("volume", drink.default_volume_ml),
        drink.aliases,
    )
    pure_alcohol_ml = (volume * abv / 100).quantize(Decimal("0.01"))
    return DrinkCalculation(effective_drink, volume, pure_alcohol_ml)
