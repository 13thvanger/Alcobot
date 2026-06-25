from datetime import date
from decimal import Decimal

import pytest

from app.llm import AlcoholLLMClient, LLMError


def test_parse_plain_json() -> None:
    result = AlcoholLLMClient._parse_result(
        '{"pure_alcohol_ml": 25, "items": [], "summary": "ok"}'
    )
    assert result["pure_alcohol_ml"] == 25


def test_parse_fenced_json() -> None:
    result = AlcoholLLMClient._parse_result(
        '```json\n{"pure_alcohol_ml": 25.5, "items": []}\n```'
    )
    assert Decimal(str(result["pure_alcohol_ml"])) == Decimal("25.5")


def test_reject_non_json() -> None:
    with pytest.raises(LLMError):
        AlcoholLLMClient._parse_result("примерно 25 мл")


def test_extract_text_content() -> None:
    content, reason = AlcoholLLMClient._extract_content(
        {
            "choices": [
                {
                    "message": {"content": '{"pure_alcohol_ml": 25}'},
                    "finish_reason": "stop",
                }
            ]
        }
    )
    assert content == '{"pure_alcohol_ml": 25}'
    assert reason == ""


def test_extract_null_content_reports_token_limit() -> None:
    content, reason = AlcoholLLMClient._extract_content(
        {
            "choices": [
                {
                    "message": {"content": None, "refusal": None, "tool_calls": []},
                    "finish_reason": "length",
                }
            ]
        }
    )
    assert content is None
    assert reason == "достигнут лимит токенов"


def test_parse_consumed_on() -> None:
    today = date(2026, 6, 25)
    assert AlcoholLLMClient._parse_consumed_on("2026-05-24", today) == date(2026, 5, 24)
    assert AlcoholLLMClient._parse_consumed_on(None, today) == today


def test_reject_future_consumed_on() -> None:
    with pytest.raises(LLMError):
        AlcoholLLMClient._parse_consumed_on("2026-06-26", date(2026, 6, 25))
