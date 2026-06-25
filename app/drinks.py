"""Детерминированный калькулятор для короткой формы команды /add."""

import re
from dataclasses import dataclass
from datetime import date
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
    consumed_on: date | None = None

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
            result = {
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
            if self.consumed_on is not None:
                result["consumed_on"] = self.consumed_on.isoformat()
            return result
        result = {
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
        if self.consumed_on is not None:
            result["consumed_on"] = self.consumed_on.isoformat()
        return result


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
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
NUMERIC_DATE_PATTERN = re.compile(
    r"^(?P<day>\d{1,2})[./](?P<month>\d{1,2})(?:[./](?P<year>\d{4}))?$"
)
RUSSIAN_MONTHS = {
    "январь": 1,
    "января": 1,
    "февраль": 2,
    "февраля": 2,
    "март": 3,
    "марта": 3,
    "апрель": 4,
    "апреля": 4,
    "май": 5,
    "мая": 5,
    "июнь": 6,
    "июня": 6,
    "июль": 7,
    "июля": 7,
    "август": 8,
    "августа": 8,
    "сентябрь": 9,
    "сентября": 9,
    "октябрь": 10,
    "октября": 10,
    "ноябрь": 11,
    "ноября": 11,
    "декабрь": 12,
    "декабря": 12,
}
SERVING_WORDS = {"glass", "shot", "бокал", "шот", "стопка"}


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


def _closest_past_date(day: int, month: int, today: date, year: int | None = None) -> date | None:
    """Построить дату; без года выбрать последнюю такую дату не позднее today."""
    candidate_year = year or today.year
    try:
        candidate = date(candidate_year, month, day)
    except ValueError:
        return None
    if year is None and candidate > today:
        try:
            candidate = date(candidate_year - 1, month, day)
        except ValueError:
            return None
    if candidate > today:
        return None
    return candidate


def _extract_date(tokens: list[str], today: date) -> tuple[date | None, list[str]] | None:
    """Извлечь не более одной даты, сохранив остальные аргументы."""
    found: date | None = None
    consumed_indexes: set[int] = set()

    for index, token in enumerate(tokens):
        candidate: date | None = None
        if ISO_DATE_PATTERN.fullmatch(token):
            try:
                candidate = date.fromisoformat(token)
            except ValueError:
                return None
            if candidate > today:
                return None
        else:
            match = NUMERIC_DATE_PATTERN.fullmatch(token)
            if match:
                candidate = _closest_past_date(
                    int(match.group("day")),
                    int(match.group("month")),
                    today,
                    int(match.group("year")) if match.group("year") else None,
                )
                if candidate is None:
                    return None
        if candidate is not None:
            if found is not None:
                return None
            found = candidate
            consumed_indexes.add(index)

    # Дата с русским месяцем занимает 2 или 3 токена: "24 мая [2026]".
    for index, token in enumerate(tokens):
        if index in consumed_indexes or token not in RUSSIAN_MONTHS:
            continue
        day_index: int | None = None
        if index > 0 and tokens[index - 1].isdigit():
            day_index = index - 1
        elif index + 1 < len(tokens) and tokens[index + 1].isdigit():
            day_index = index + 1
        if day_index is None:
            continue

        year: int | None = None
        year_index: int | None = None
        for candidate_index in (max(index, day_index) + 1, min(index, day_index) - 1):
            if (
                0 <= candidate_index < len(tokens)
                and candidate_index not in {index, day_index}
                and len(tokens[candidate_index]) == 4
                and tokens[candidate_index].isdigit()
            ):
                year = int(tokens[candidate_index])
                year_index = candidate_index
                break

        candidate = _closest_past_date(
            int(tokens[day_index]),
            RUSSIAN_MONTHS[token],
            today,
            year,
        )
        if candidate is None or found is not None:
            return None
        found = candidate
        consumed_indexes.update({index, day_index})
        if year_index is not None:
            consumed_indexes.add(year_index)

    remaining = [token for index, token in enumerate(tokens) if index not in consumed_indexes]
    return found, remaining


def calculate_short_add(
    text: str,
    overrides: dict[str, dict[str, Decimal]] | None = None,
    current_date: date | None = None,
) -> DrinkCalculation | None:
    """Parse `/add drink` with volume, ABV and date in any following order.

    Для свободного текста возвращается None, после чего обработчик вызывает LLM.
    """
    # Цепочки методов читаются слева направо: lower -> strip -> split.
    parts = text.lower().strip().split()
    if not parts:
        return None

    if len(parts) == 1:
        volume = _parse_volume(parts[0])
        if volume is not None:
            return DrinkCalculation(None, volume, volume)

    drink = DRINK_BY_ALIAS.get(parts[0])
    if drink is None:
        return None

    extracted = _extract_date(parts[1:], current_date or date.today())
    if extracted is None:
        return None
    consumed_on, arguments = extracted

    volume: Decimal | None = None
    explicit_abv: Decimal | None = None
    for argument in arguments:
        # Слова тары не меняют стандартную порцию группы напитка:
        # beer glass=500 мл, wine glass=150 мл, spirit shot=50 мл.
        if argument in SERVING_WORDS:
            continue
        parsed_abv = _parse_abv(argument)
        if parsed_abv is not None:
            if explicit_abv is not None:
                return None
            explicit_abv = parsed_abv
            continue
        parsed_volume = _parse_volume(argument)
        if parsed_volume is not None:
            if volume is not None:
                return None
            volume = parsed_volume
            continue
        return None

    # ``x or {}`` возвращает первый truthy-операнд. None и пустой dict считаются
    # false. get(key, default) не выбрасывает исключение при отсутствии ключа.
    override = (overrides or {}).get(drink.key, {})
    if volume is None:
        volume = override.get("volume", drink.default_volume_ml)
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
    return DrinkCalculation(effective_drink, volume, pure_alcohol_ml, consumed_on)
