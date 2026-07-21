"""US earnings calendar for the unified daily brief.

Built-in quarterly earnings windows for the most-watched large caps. Dates are
scheduled approximations of each company's reporting cadence; entries are
labeled as estimated. No external API key required; can later be replaced by an
FMP earnings-calendar adapter without changing the caller contract.
"""

from __future__ import annotations

from datetime import date

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
