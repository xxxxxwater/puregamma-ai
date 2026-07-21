"""Macroeconomic event calendar for the unified daily brief.

Built-in schedule of the highest-impact recurring US macro events (FOMC rate
decisions, CPI releases, Nonfarm Payrolls). No external API key required; the
schedule is deterministic and safe for template rendering. When a FRED API key
is configured, this module can later be extended to fetch confirmed dates.
"""

from __future__ import annotations

import calendar
from datetime import date

# 2026 FOMC rate-decision dates (second day of each meeting).
_FOMC_2026 = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
]

# Approximate 2026 CPI release dates (BLS monthly schedule).
_CPI_2026 = [
    date(2026, 1, 13), date(2026, 2, 11), date(2026, 3, 11), date(2026, 4, 10),
    date(2026, 5, 12), date(2026, 6, 10), date(2026, 7, 14), date(2026, 8, 12),
    date(2026, 9, 11), date(2026, 10, 13), date(2026, 11, 10), date(2026, 12, 10),
]


def _first_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    offset = (calendar.FRIDAY - first.weekday()) % 7
    return first.replace(day=1 + offset)


def _nfp_dates(year: int) -> list[date]:
    return [_first_friday(year, month) for month in range(1, 13)]


def events_for(day: date, locale: str = "en") -> list[str]:
    """Return today's scheduled macro events as short labels."""
    zh = locale == "zh"
    events: list[str] = []
    if day in _FOMC_2026:
        events.append("FOMC 利率决议日" if zh else "FOMC rate decision")
    if day in _CPI_2026:
        events.append("美国 CPI 发布" if zh else "US CPI release")
    if day in _nfp_dates(day.year):
        events.append("非农就业报告" if zh else "Nonfarm Payrolls")
    return events
