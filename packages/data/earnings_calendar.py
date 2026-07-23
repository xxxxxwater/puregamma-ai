"""US earnings calendar for the unified daily brief.

Built-in quarterly earnings windows for the most-watched large caps. Dates are
scheduled approximations of each company's reporting cadence; entries are
labeled as estimated. No external API key required; can later be replaced by an
FMP earnings-calendar adapter without changing the caller contract.
"""

from __future__ import annotations

from datetime import date, timedelta

# ticker -> list of (month, day) reporting windows for 2026 (estimated).
_EARNINGS_2026: dict[str, list[tuple[int, int]]] = {
    "AAPL": [(1, 29), (4, 30), (7, 30), (10, 29)],
    "MSFT": [(1, 27), (4, 28), (7, 28), (10, 27)],
    "NVDA": [(2, 25), (5, 27), (8, 26), (11, 18)],
    "TSLA": [(1, 28), (4, 21), (7, 22), (10, 20)],
    "GOOGL": [(2, 3), (4, 23), (7, 21), (10, 27)],
    "AMZN": [(2, 5), (4, 30), (7, 30), (10, 29)],
    "META": [(1, 28), (4, 29), (7, 29), (10, 28)],
    "JPM": [(1, 15), (4, 14), (7, 14), (10, 13)],
    "MSTR": [(2, 4), (4, 30), (7, 30), (10, 29)],
}


def earnings_for(day: date, locale: str = "en") -> list[str]:
    """Return today's estimated earnings as short labels."""
    zh = locale == "zh"
    hits = [ticker for ticker, windows in _EARNINGS_2026.items() if any(day == date(2026, month, dom) for month, dom in windows)]
    if not hits:
        return []
    suffix = "财报（预计）" if zh else "earnings (est.)"
    return [f"{ticker} {suffix}" for ticker in sorted(hits)]


def upcoming_earnings(day: date, days: int = 7, locale: str = "en") -> list[str]:
    """Return estimated earnings within the next `days` days as dated labels.

    Entries stay labeled as estimated because the built-in calendar tracks
    reporting cadence, not confirmed dates.
    """
    zh = locale == "zh"
    items: list[tuple[date, str]] = []
    for ticker, windows in _EARNINGS_2026.items():
        for month, dom in windows:
            report_day = date(2026, month, dom)
            if day <= report_day < day + timedelta(days=days):
                items.append((report_day, ticker))
    if not items:
        return []
    items.sort()
    suffix = "财报（预计）" if zh else "earnings (est.)"
    return [f"{ticker} {report_day.strftime('%m-%d')} {suffix}" for report_day, ticker in items]
