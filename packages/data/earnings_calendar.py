"""US earnings calendar with two clearly separated trust tiers.

CONFIRMED tier (production facts):
    ``fetch_confirmed_earnings`` / ``upcoming_confirmed_earnings`` read the
    public Nasdaq earnings calendar API and return only real fetched rows.
    Provider failures raise :class:`ProviderUnavailable`; callers must record
    health and never fall back to estimated dates.

ESTIMATED tier (legacy cadence hints):
    ``earnings_for`` / ``upcoming_earnings`` keep the built-in quarterly
    reporting-cadence windows for the most-watched large caps. Entries are
    approximations labeled "(est.)"/"（预计）" and must NOT feed confirmed
    research facts, alerts or impact computations.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NASDAQ_EARNINGS_API_URL = "https://api.nasdaq.com/api/calendar/earnings"
NASDAQ_EARNINGS_PAGE_URL = "https://www.nasdaq.com/market-activity/earnings"
_CACHE_KEY_PREFIX = "pg:calendar:earnings:"
_CACHE_TTL_SECONDS = 6 * 3600
_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


class ProviderUnavailable(RuntimeError):
    """The confirmed earnings provider could not serve real data."""


def _cache_key(day: date) -> str:
    return f"{_CACHE_KEY_PREFIX}{day.isoformat()}"


def _cache_read(day: date) -> list[dict] | None:
    """Best-effort Redis cache read; any backend problem falls back to no-cache."""
    try:
        from apps.api.redis_client import get_redis

        raw = get_redis().get(_cache_key(day))
        if raw is None:
            return None
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else None
    except Exception:
        return None


def _cache_write(day: date, rows: list[dict]) -> None:
    """Best-effort Redis cache write; failures are ignored (no-cache mode)."""
    try:
        from apps.api.redis_client import get_redis

        get_redis().set(_cache_key(day), json.dumps(rows), ex=_CACHE_TTL_SECONDS)
    except Exception:
        pass


def parse_nasdaq_earnings(payload: dict, day: date) -> list[dict]:
    """Normalize one Nasdaq calendar payload into confirmed earning rows.

    ``data.rows`` items carry symbol, name, time (label), epsForecast,
    marketCap and asOf. Days whose ``rows`` is null simply have no confirmed
    earnings and return an empty list.
    """
    if not isinstance(payload, dict) or "data" not in payload:
        raise ProviderUnavailable("Nasdaq earnings payload missing 'data'")
    data = payload.get("data") or {}
    rows = data.get("rows")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ProviderUnavailable("Nasdaq earnings 'rows' is not a list")
    results: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        results.append(
            {
                "symbol": symbol,
                "name": str(row.get("name") or symbol).strip(),
                "time_label": str(row.get("time") or "").strip() or None,
                "eps_forecast": row.get("epsForecast") or None,
                "market_cap": row.get("marketCap") or None,
                "source_url": NASDAQ_EARNINGS_PAGE_URL,
                "as_of": day.isoformat(),
                "confirmed": True,
            }
        )
    return results


def fetch_confirmed_earnings(day: date, session: Any = None) -> list[dict]:
    """Fetch the CONFIRMED earnings calendar for one day from Nasdaq.

    Returns only real fetched rows. Raises :class:`ProviderUnavailable` on any
    provider, transport or payload problem so callers can record health instead
    of fabricating dates. Results are cached in Redis for 6 hours when
    available; cache failures degrade to plain no-cache HTTP fetches.
    """
    cached = _cache_read(day)
    if cached is not None:
        return cached
    from apps.api.config import get_settings

    settings = get_settings()
    client = session if session is not None else httpx
    try:
        response = client.get(
            NASDAQ_EARNINGS_API_URL,
            params={"date": day.isoformat()},
            headers=_REQUEST_HEADERS,
            timeout=settings.provider_http_timeout_seconds,
        )
        response.raise_for_status()
        content = response.content
        if len(content) > settings.provider_max_response_bytes:
            raise ProviderUnavailable(
                f"Nasdaq earnings response exceeded {settings.provider_max_response_bytes} bytes"
            )
        payload = response.json()
    except ProviderUnavailable:
        raise
    except Exception as exc:
        raise ProviderUnavailable(
            f"Nasdaq earnings calendar unavailable for {day.isoformat()}: {str(exc)[:200]}"
        ) from exc
    rows = parse_nasdaq_earnings(payload, day)
    _cache_write(day, rows)
    return rows


def upcoming_confirmed_earnings(start_day: date, days: int = 7) -> list[dict]:
    """Return CONFIRMED earnings rows for ``start_day`` .. ``start_day + days``.

    Days without confirmed rows (``rows`` is null) are skipped. Provider
    failures propagate as :class:`ProviderUnavailable`; the research pipeline
    catches it and records source health.
    """
    items: list[dict] = []
    for offset in range(max(0, days)):
        day = start_day + timedelta(days=offset)
        rows = fetch_confirmed_earnings(day)
        if not rows:
            continue
        items.extend(rows)
    return items


# ---------------------------------------------------------------------------
# ESTIMATED tier: built-in quarterly reporting cadence (legacy brief hints).
# These dates are approximations of each company's reporting cadence, always
# labeled "(est.)"/"（预计）". They are NOT confirmed facts and must never be
# consumed by the research event pipeline, alerts or impact computations.
# ---------------------------------------------------------------------------

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
    """ESTIMATED tier: return today's estimated earnings as short labels.

    Dates come from the built-in reporting-cadence table, not a confirmed
    provider. Do not use for confirmed research facts.
    """
    zh = locale == "zh"
    hits = [ticker for ticker, windows in _EARNINGS_2026.items() if any(day == date(2026, month, dom) for month, dom in windows)]
    if not hits:
        return []
    suffix = "财报（预计）" if zh else "earnings (est.)"
    return [f"{ticker} {suffix}" for ticker in sorted(hits)]


def upcoming_earnings(day: date, days: int = 7, locale: str = "en") -> list[str]:
    """ESTIMATED tier: return estimated earnings within the next `days` days.

    Entries stay labeled as estimated because the built-in calendar tracks
    reporting cadence, not confirmed dates. Do not use for confirmed research
    facts.
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
