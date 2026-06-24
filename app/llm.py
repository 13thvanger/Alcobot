import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from app.config import Settings

SYSTEM_PROMPT = """
Ты преобразуешь описание выпитых алкогольных напитков в миллилитры чистого этанола.
Верни ТОЛЬКО валидный JSON без markdown и комментариев:
{
  "pure_alcohol_ml": 42.5,
  "items": [
    {
      "name": "пиво",
      "volume_ml": 500,
      "abv_percent": 5,
      "pure_alcohol_ml": 25
    }
  ],
  "summary": "Краткое объяснение расчета"
}

Формула для каждого напитка: объем напитка в мл * крепость в процентах / 100.
Учитывай разговорные единицы: бутылка, банка, бокал, стопка и т.п.
Если объем или крепость не указаны, используй наиболее типичное значение и явно отрази
допущение в summary. Учитывай только алкоголь, который пользователь сообщает как выпитый.
Не включай скрытые рассуждения. Значение pure_alcohol_ml не может быть отрицательным.
""".strip()


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class AlcoholEstimate:
    pure_alcohol_ml: Decimal
    items: list[dict]
    summary: str
    raw: dict


class AlcoholLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.api_url = settings.llm_api_url
        self.api_key = settings.llm_api_key.get_secret_value()
        self.model = settings.llm_model
        self.client = httpx.AsyncClient(
            timeout=settings.llm_timeout_seconds,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Alcobot/0.1 (+telegram-bot)",
            },
        )

    async def estimate(
        self,
        description: str,
        *,
        temperature: float = 0,
        max_tokens: int = 2000,
    ) -> AlcoholEstimate:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = await self.client.post(self.api_url, json=payload)
            response.raise_for_status()
            envelope = response.json()
            content = envelope["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("Не удалось получить корректный ответ от модели") from exc

        result = self._parse_result(content)
        try:
            amount = Decimal(str(result["pure_alcohol_ml"])).quantize(Decimal("0.01"))
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise LLMError("Модель вернула некорректное количество алкоголя") from exc

        if amount < 0 or amount > Decimal("10000"):
            raise LLMError("Модель вернула количество алкоголя вне допустимого диапазона")

        items = result.get("items", [])
        if not isinstance(items, list):
            items = []
        summary = str(result.get("summary", "")).strip()
        return AlcoholEstimate(amount, items, summary, result)

    @staticmethod
    def _parse_result(content: str) -> dict:
        text = content.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.I)
        if fenced:
            text = fenced.group(1)
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("Модель вернула невалидный JSON") from exc
        if not isinstance(result, dict):
            raise LLMError("Модель вернула JSON неверного типа")
        return result

    async def close(self) -> None:
        await self.client.aclose()
