"""Загрузка и проверка конфигурации из переменных окружения и файла .env."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Pydantic читает одноимённые переменные окружения без ручного getenv.
    # Имена полей — snake_case, переменные окружения могут быть UPPER_CASE.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ``name: Type`` — аннотация типа. Отсутствие ``= default`` означает, что
    # значение обязательно. SecretStr маскирует секрет при печати объекта.
    telegram_bot_token: SecretStr
    admin_telegram_ids: str = ""
    database_url: str

    llm_api_key: SecretStr
    llm_api_url: str = "https://bridge-back.admlr.lipetsk.ru/api/v1/chat/completions"
    llm_model: str = "cifra48/agent"
    llm_timeout_seconds: float = Field(default=60, gt=0, le=300)

    app_timezone: str = "Europe/Moscow"
    log_level: str = "INFO"

    @property
    def timezone(self) -> ZoneInfo:
        # @property превращает метод в вычисляемое read-only свойство:
        # settings.timezone вместо settings.timezone().
        return ZoneInfo(self.app_timezone)

    @property
    def admin_ids(self) -> set[int]:
        # set — множество уникальных значений; ближайший аналог std::set,
        # но реализован как hash set и обычно имеет O(1) для проверки ``in``.
        result: set[int] = set()
        for value in self.admin_telegram_ids.split(","):
            value = value.strip()
            if value:
                result.add(int(value))
        return result


@lru_cache
def get_settings() -> Settings:
    # Декоратор кэширует результат: Settings создаётся только при первом вызове.
    # Последующие вызовы возвращают тот же объект.
    return Settings()  # type: ignore[call-arg]
