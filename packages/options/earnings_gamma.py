from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

from redis import Redis
from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.agents.llm.provider_factory import get_llm_provider

logger = logging.getLogger(__name__)

_EARNINGS_CACHE: dict[str, list[dict]] = {}
_EARNINGS_LOCK = RLock()
_EARNINGS_CACHE_TTL_SECONDS = 8 * 24 * 60 * 60
_NEW_YORK = ZoneInfo("America/New_York")


def _cache_key(language: str) -> str:
    return f"puregamma:options:earnings:{language}"


def _redis_client() -> Redis:
    return Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def _store_candidates(language: str, candidates: list[dict]) -> None:
    with _EARNINGS_LOCK:
        _EARNINGS_CACHE[language] = candidates
    payload = json.dumps(
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "candidates": candidates,
        }
    )
    try:
        _redis_client().setex(
            _cache_key(language), _EARNINGS_CACHE_TTL_SECONDS, payload
        )
    except Exception as exc:
        logger.warning(
            "earnings_gamma_cache_write_failed language=%s error=%s",
            language,
            exc,
        )


def _observed_holiday(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    return cursor - timedelta(days=(cursor.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    length = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * length) // 451
    month = (h + length - 7 * m + 114) // 31
    day = ((h + length - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nyse_holidays(year: int) -> set[date]:
    return {
        _observed_holiday(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed_holiday(date(year, 6, 19)),
        _observed_holiday(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed_holiday(date(year, 12, 25)),
    }


def is_us_equity_trading_day(day: date | None = None) -> bool:
    market_day = day or datetime.now(_NEW_YORK).date()
    if market_day.weekday() >= 5:
        return False
    holidays = _nyse_holidays(market_day.year) | _nyse_holidays(
        market_day.year + 1
    )
    return market_day not in holidays


def _search_documents_for_symbol(db: Session, symbol: str) -> str:
    from packages.database.models import NormalizedDocument

    try:
        docs = (
            db.query(NormalizedDocument)
            .filter(
                cast(NormalizedDocument.symbols, String).contains(f'"{symbol}"'),
                NormalizedDocument.license_status != "expired",
            )
            .order_by(NormalizedDocument.published_at.desc())
            .limit(5)
            .all()
        )
    except Exception as exc:
        db.rollback()
        logger.warning(
            "earnings_gamma_news_lookup_failed symbol=%s error=%s", symbol, exc
        )
        return ""
    if not docs:
        return ""
    return " | ".join(
        doc.summary or doc.title for doc in docs if doc.summary or doc.title
    )


def _discover_earnings_stocks(
    db: Session, language: str
) -> list[dict[str, Any]]:
    provider = get_llm_provider()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    locale_instruction = (
        "Use Chinese company names when commonly available. "
        if language == "zh"
        else "Use English company names. "
    )
    prompt = (
        f"Today is {today}. List US-listed stocks with upcoming earnings in the "
        f"next 7 days starting on {today}. {locale_instruction}\n"
        "Output ONLY a JSON array in this exact format, nothing else:\n"
        '[{"symbol": "AAPL", "name": "Apple Inc.", '
        '"earnings_date": "YYYY-MM-DD", "sector": "Technology", '
        '"market_cap_category": "large", "options_available": true}]\n'
        "Requirements:\n"
        "- List 8-15 stocks\n"
        "- market_cap_category: large (>$50B), mid ($2-50B), small (<$2B)\n"
        "- Output ONLY the JSON array\n"
    )

    try:
        result = provider.complete(
            prompt,
            task_type="agent_chat",
            locale=language,
            user_id=None,
            db=db,
        )
    except Exception:
        return _fallback_earnings(language)

    try:
        start = result.find("[")
        end = result.rfind("]") + 1
        if start >= 0 and end > start:
            stocks = json.loads(result[start:end])
            if isinstance(stocks, list) and stocks:
                return stocks
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return _fallback_earnings(language)


def _fallback_earnings(language: str) -> list[dict]:
    return [
        {"symbol": "AAPL", "name": "Apple Inc.", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "MSTR", "name": "Strategy (MicroStrategy)", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "COIN", "name": "Coinbase Global", "earnings_date": "", "sector": "Financial", "market_cap_category": "large", "options_available": True},
        {"symbol": "TSLA", "name": "Tesla Inc.", "earnings_date": "", "sector": "Consumer", "market_cap_category": "large", "options_available": True},
        {"symbol": "AMD", "name": "Advanced Micro Devices", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "SQ", "name": "Block Inc.", "earnings_date": "", "sector": "Financial", "market_cap_category": "large", "options_available": True},
    ]


def _score_stock(stock: dict, db: Session) -> dict:
    symbol = stock.get("symbol", "UNKNOWN")
    news_context = _search_documents_for_symbol(db, symbol)
    sector_score = _sector_multiplier(stock.get("sector", ""))
    cap_score = _cap_score(stock.get("market_cap_category", "mid"))
    news_bonus = min(20, len(news_context.split()) / 10) if news_context else 5
    base = sector_score * 30 + cap_score * 30 + 15 + news_bonus
    score = round(min(95, base), 1)

    rationale = ["earnings catalyst"]
    if news_context:
        rationale.append("news coverage detected")
    if sector_score >= 1.0:
        rationale.append("high-volatility sector")

    return {
        "symbol": symbol,
        "name": stock.get("name", symbol),
        "earnings_date": stock.get("earnings_date", ""),
        "sector": stock.get("sector", ""),
        "market_cap_category": stock.get("market_cap_category", "mid"),
        "research_score": score,
        "rationale": rationale,
        "news_snippet": (news_context or "")[:200],
        "execution_enabled": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _sector_multiplier(sector: str) -> float:
    return {
        "Technology": 1.0,
        "Financial": 0.9,
        "Consumer": 0.85,
        "Energy": 0.8,
        "Healthcare": 0.75,
    }.get(sector, 0.7)


def _cap_score(cap: str) -> float:
    return {"large": 1.0, "mid": 0.8, "small": 0.5}.get(cap, 0.6)


def refresh_earnings_candidates(
    db: Session, language: str = "en"
) -> list[dict]:
    stocks = _discover_earnings_stocks(db, language)
    candidates = []
    for stock in stocks:
        try:
            candidates.append(_score_stock(stock, db))
        except Exception as exc:
            logger.warning(
                "earnings_gamma_candidate_failed symbol=%s error=%s",
                stock.get("symbol", "UNKNOWN"),
                exc,
            )
    candidates.sort(key=lambda row: row["research_score"], reverse=True)
    for cache_language in ("en", "zh"):
        _store_candidates(cache_language, candidates)
    return candidates


def get_earnings_candidates(language: str = "en") -> list[dict]:
    try:
        cached = _redis_client().get(_cache_key(language))
        if cached:
            payload = json.loads(cached)
            candidates = payload.get("candidates", [])
            if isinstance(candidates, list):
                with _EARNINGS_LOCK:
                    _EARNINGS_CACHE[language] = candidates
                return candidates
    except Exception as exc:
        logger.warning(
            "earnings_gamma_cache_read_failed language=%s error=%s", language, exc
        )
    with _EARNINGS_LOCK:
        return _EARNINGS_CACHE.get(language, [])


def force_refresh_earnings(
    db: Session, language: str = "en"
) -> list[dict]:
    return refresh_earnings_candidates(db, language)
