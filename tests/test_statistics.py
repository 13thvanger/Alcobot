from datetime import date
from decimal import Decimal

from app.statistics import EntryValue, calculate_statistics


def entry(day: str, amount: str) -> EntryValue:
    return EntryValue(date.fromisoformat(day), Decimal(amount))


def test_statistics_merge_entries_and_calculate_streaks() -> None:
    result = calculate_statistics(
        [
            entry("2026-01-01", "10"),
            entry("2026-01-01", "15"),
            entry("2026-01-02", "20"),
            entry("2026-01-04", "30"),
        ],
        date(2026, 2, 1),
    )

    assert result is not None
    assert result.total == Decimal("75")
    assert result.entries_count == 4
    assert result.drinking_days == 3
    assert result.average_per_month == Decimal("37.5")
    assert result.average_per_year == Decimal("450")
    assert result.strongest_month == (2026, 1, Decimal("75"))
    assert result.strongest_day == (date(2026, 1, 4), Decimal("30"))
    assert result.longest_streak == 2
    assert result.current_streak == 0


def test_current_streak_counts_yesterday() -> None:
    result = calculate_statistics(
        [entry("2026-06-22", "10"), entry("2026-06-23", "10")],
        date(2026, 6, 24),
    )
    assert result is not None
    assert result.current_streak == 2


def test_statistics_only_include_current_year_from_january() -> None:
    result = calculate_statistics(
        [
            entry("2025-12-31", "100"),
            entry("2026-03-01", "60"),
        ],
        date(2026, 6, 24),
    )
    assert result is not None
    assert result.total == Decimal("60")
    assert result.average_per_month == Decimal("10")
    assert result.average_per_year == Decimal("120")


def test_empty_statistics() -> None:
    assert calculate_statistics([], date(2026, 1, 1)) is None
