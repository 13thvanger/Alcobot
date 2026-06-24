from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import BotSetting

SETTING_DESCRIPTIONS = {
    "timezone": "Часовой пояс для даты записей",
    "llm_temperature": "Температура LLM от 0 до 2",
    "llm_max_tokens": "Максимальное число токенов ответа LLM",
}


@dataclass(frozen=True)
class RuntimeConfig:
    timezone: ZoneInfo
    llm_temperature: float
    llm_max_tokens: int
    drink_overrides: dict[str, dict[str, Decimal]]


async def get_all_settings(session: AsyncSession) -> dict[str, str]:
    rows = await session.execute(select(BotSetting.key, BotSetting.value))
    return dict(rows)


async def get_runtime_config(session: AsyncSession, defaults: Settings) -> RuntimeConfig:
    values = await get_all_settings(session)
    timezone = ZoneInfo(values.get("timezone", defaults.app_timezone))
    temperature = float(values.get("llm_temperature", "0"))
    max_tokens = int(values.get("llm_max_tokens", "2000"))
    overrides: dict[str, dict[str, Decimal]] = {}
    for key, value in values.items():
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "drink" and parts[2] in {"abv", "volume"}:
            overrides.setdefault(parts[1], {})[parts[2]] = Decimal(value)
    return RuntimeConfig(timezone, temperature, max_tokens, overrides)


def validate_setting(key: str, value: str, known_drinks: set[str]) -> str:
    value = value.strip()
    if key == "timezone":
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Неизвестный часовой пояс") from exc
        return value
    if key == "llm_temperature":
        number = _decimal(value)
        if number < 0 or number > 2:
            raise ValueError("Температура должна быть от 0 до 2")
        return str(number)
    if key == "llm_max_tokens":
        try:
            number = int(value)
        except ValueError as exc:
            raise ValueError("Количество токенов должно быть целым числом") from exc
        if number < 100 or number > 4000:
            raise ValueError("Количество токенов должно быть от 100 до 4000")
        return str(number)

    parts = key.split(".")
    if len(parts) != 3 or parts[0] != "drink" or parts[1] not in known_drinks:
        raise ValueError("Неизвестная настройка")
    number = _decimal(value)
    if parts[2] == "abv" and Decimal("0.1") <= number <= 100:
        return str(number)
    if parts[2] == "volume" and Decimal("1") <= number <= 10000:
        return str(number)
    raise ValueError("Для напитка доступны поля abv и volume с допустимым числом")


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Значение должно быть числом") from exc


async def set_setting(
    session: AsyncSession, key: str, value: str, admin_id: int
) -> BotSetting:
    setting = await session.get(BotSetting, key)
    if setting is None:
        setting = BotSetting(key=key, value=value, updated_by=admin_id)
        session.add(setting)
    else:
        setting.value = value
        setting.updated_by = admin_id
    await session.commit()
    return setting


async def delete_setting(session: AsyncSession, key: str) -> bool:
    setting = await session.get(BotSetting, key)
    if setting is None:
        return False
    await session.delete(setting)
    await session.commit()
    return True
