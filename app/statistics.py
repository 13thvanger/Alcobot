from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class EntryValue:
    consumed_on: date
    amount: Decimal


@dataclass(frozen=True)
class AlcoholStatistics:
    total: Decimal
    entries_count: int
    drinking_days: int
    average_per_month: Decimal
    average_per_year: Decimal
    strongest_month: tuple[int, int, Decimal]
    strongest_day: tuple[date, Decimal]
    longest_streak: int
    current_streak: int


def _streaks(days: list[date], today: date) -> tuple[int, int]:
    if not days:
        return 0, 0

    longest = current_run = 1
    for previous, current in zip(days, days[1:], strict=False):
        if current == previous + timedelta(days=1):
            current_run += 1
            longest = max(longest, current_run)
        else:
            current_run = 1

    last_day = days[-1]
    current_streak = current_run if last_day in {today, today - timedelta(days=1)} else 0
    return longest, current_streak


def calculate_statistics(entries: list[EntryValue], today: date) -> AlcoholStatistics | None:
    positive = [
        entry
        for entry in entries
        if entry.amount > 0 and entry.consumed_on.year == today.year
    ]
    if not positive:
        return None

    by_day: dict[date, Decimal] = defaultdict(Decimal)
    by_month: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    total = Decimal()
    for entry in positive:
        total += entry.amount
        by_day[entry.consumed_on] += entry.amount
        by_month[(entry.consumed_on.year, entry.consumed_on.month)] += entry.amount

    strongest_month_key, strongest_month_amount = max(by_month.items(), key=lambda item: item[1])
    strongest_day, strongest_day_amount = max(by_day.items(), key=lambda item: item[1])
    longest_streak, current_streak = _streaks(sorted(by_day), today)

    return AlcoholStatistics(
        total=total,
        entries_count=len(positive),
        drinking_days=len(by_day),
        average_per_month=total / today.month,
        average_per_year=total / today.month * 12,
        strongest_month=(*strongest_month_key, strongest_month_amount),
        strongest_day=(strongest_day, strongest_day_amount),
        longest_streak=longest_streak,
        current_streak=current_streak,
    )
