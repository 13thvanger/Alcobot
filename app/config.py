from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
        return ZoneInfo(self.app_timezone)

    @property
    def admin_ids(self) -> set[int]:
        result: set[int] = set()
        for value in self.admin_telegram_ids.split(","):
            value = value.strip()
            if value:
                result.add(int(value))
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
