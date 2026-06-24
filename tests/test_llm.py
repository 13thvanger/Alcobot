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

