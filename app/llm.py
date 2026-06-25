"""HTTP-клиент LLM и преобразование её JSON-ответа в типизированный объект."""

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from app.config import Settings

SYSTEM_PROMPT = """
Ты преобразуешь описание выпитых алкогольных напитков в миллилитры чистого этанола.
Верни ТОЛЬКО валидный JSON без markdown и комментариев:
{
  "pure_alcohol_ml": 42.5,
  "consumed_on": "2026-05-24",
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
Учитывай разговорные единицы и названия тары: бутылка, пузырь, банка, бокал,
стопка и т.п. "Пузырь" обычно означает бутылку. Если сказано "пузырь водки"
без объема, используй типичный объем бутылки водки 500 мл.
Если пользователь явно указал крепость, например 4% или 12%, обязательно используй
именно это значение вместо типичной крепости напитка.
Если объем или крепость не указаны, используй наиболее типичное значение и явно отрази
допущение в summary. Учитывай только алкоголь, который пользователь сообщает как выпитый.
Определи дату употребления из текста и верни consumed_on в формате YYYY-MM-DD.
Если указаны только день и месяц, выбери ближайшую прошедшую такую дату относительно
переданной текущей даты. Если даты нет, используй текущую дату.
Не вызывай инструменты. Обязательно помести готовый JSON в поле message.content.
Не включай скрытые рассуждения. Значение pure_alcohol_ml не может быть отрицательным.
""".strip()

RETRY_PROMPT = """
Предыдущий ответ не содержал текста в message.content.
Не вызывай инструменты и не возвращай пустой content.
Ответь сейчас только итоговым JSON требуемого формата в message.content.
""".strip()


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class AlcoholEstimate:
    # Отдельный тип результата лучше "сырого" dict: IDE знает имена и типы полей.
    pure_alcohol_ml: Decimal
    items: list[dict]
    summary: str
    consumed_on: date
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
        current_date: date | None = None,
        # Одинокая * запрещает передавать следующие параметры позиционно:
        # estimate(text, temperature=0), но не estimate(text, 0).
        temperature: float = 0,
        max_tokens: int = 4000,
    ) -> AlcoholEstimate:
        # dict в Python — hash map. Его можно напрямую сериализовать в JSON.
        today = current_date or date.today()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Текущая дата: {today.isoformat()}.\n"
                    f"Описание пользователя: {description}"
                ),
            },
        ]
        content: str | None = None
        last_reason = "пустой ответ"

        # Вторая попытка нужна для reasoning-моделей: иногда они исчерпывают
        # первый лимит до формирования финального message.content.
        for attempt in range(2):
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "temperature": temperature,
                "max_tokens": max_tokens if attempt == 0 else max(max_tokens, 4000),
            }
            try:
                response = await self.client.post(self.api_url, json=payload)
                response.raise_for_status()
                envelope = response.json()
                content, last_reason = self._extract_content(envelope)
            except httpx.HTTPError as exc:
                raise LLMError("Ошибка HTTP при обращении к модели") from exc
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise LLMError("Модель вернула ответ неизвестного формата") from exc

            if content is not None:
                break
            messages.append({"role": "user", "content": RETRY_PROMPT})

        if content is None:
            raise LLMError(f"Модель не вернула текстовый JSON: {last_reason}")

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
        consumed_on = self._parse_consumed_on(result.get("consumed_on"), today)
        result["consumed_on"] = consumed_on.isoformat()
        return AlcoholEstimate(amount, items, summary, consumed_on, result)

    @staticmethod
    def _parse_consumed_on(value: object, today: date) -> date:
        """Проверить дату модели и запретить случайные даты из будущего."""
        if value is None or value == "":
            return today
        if not isinstance(value, str):
            raise LLMError("Модель вернула дату неверного типа")
        try:
            consumed_on = date.fromisoformat(value)
        except ValueError as exc:
            raise LLMError("Модель вернула дату не в формате YYYY-MM-DD") from exc
        if consumed_on > today:
            raise LLMError("Модель определила дату употребления в будущем")
        return consumed_on

    @staticmethod
    def _extract_content(envelope: dict) -> tuple[str | None, str]:
        """Получить content и безопасное описание причины пустого ответа."""
        choice = envelope["choices"][0]
        message = choice["message"]
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content, ""

        refusal = message.get("refusal")
        if refusal:
            return None, "модель отказалась отвечать"
        if message.get("tool_calls"):
            return None, "модель попыталась вызвать инструмент"
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            return None, "достигнут лимит токенов"
        return None, f"content пуст, finish_reason={finish_reason or 'unknown'}"

    @staticmethod
    def _parse_result(content: str) -> dict:
        text = content.strip()
        # r"..." — raw string: слеши regex не нужно экранировать второй раз.
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
