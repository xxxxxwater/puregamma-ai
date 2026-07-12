from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from sqlalchemy.orm import Session

from packages.agents.llm.provider_factory import get_llm_provider

_EARNINGS_CACHE: dict[str, tuple[float, list[dict]]] = {}
_EARNINGS_LOCK = RLock()


def _search_documents_for_symbol(db: Session, symbol: str) -> str:
    from packages.database.models import NormalizedDocument

    docs = (
        db.query(NormalizedDocument)
        .filter(
            NormalizedDocument.symbols.contains(symbol),
            NormalizedDocument.license_status != "expired",
        )
        .order_by(NormalizedDocument.published_at.desc())
        .limit(5)
        .all()
    )
    if not docs:
        return ""
    return " | ".join(doc.summary or doc.title for doc in docs if doc.summary or doc.title)


def _discover_earnings_stocks(db: Session, language: str) -> list[dict[str, Any]]:
    provider = get_llm_provider()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if language == "zh":
        prompt = (
            f"今天是 {today}。请列出未来一周（{today} 至7天后）即将公布财报的美股标的。\n"
            "只输出符合以下 JSON 格式的内容，不要输出其他任何文字：\n"
            '[{"symbol": "AAPL", "name": "Apple Inc.", "earnings_date": "2026-07-14", "sector": "Technology", '
            '"market_cap_category": "large", "options_available": true}]\n'
            "要求：\n"
            "- 列出 8-15 个标的\n"
            "- market_cap_category: large(>$50B), mid($2-50B), small(<$2B)\n"
            "- 只输出 JSON 数组，不要有其他内容\n"
        )
    else:
        prompt = (
            f"Today is {today}. List US stocks with upcoming earnings in the next 7 days (from {today}).\n"
            "Output ONLY a JSON array in this exact format, nothing else:\n"
            '[{"symbol": "AAPL", "name": "Apple Inc.", "earnings_date": "2026-07-14", "sector": "Technology", '
            '"market_cap_category": "large", "options_available": true}]\n'
            "Requirements:\n"
            "- List 8-15 stocks\n"
            "- market_cap_category: large (>$50B), mid ($2-50B), small (<$2B)\n"
            "- Output ONLY the JSON array\n"
        )

    try:
        result = provider.complete(prompt, task_type="agent_chat", locale=language, user_id=None, db=db)
    except Exception:
        return _fallback_earnings(language)

    try:
        start = result.find("[")
        end = result.rfind("]") + 1
        if start >= 0 and end > start:
            stocks = json.loads(result[start:end])
            if isinstance(stocks, list) and len(stocks) > 0:
                return stocks
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return _fallback_earnings(language)


def _fallback_earnings(language: str) -> list[dict]:
    stocks = [
        {"symbol": "AAPL", "name": "Apple Inc.", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "MSTR", "name": "Strategy (MicroStrategy)", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "COIN", "name": "Coinbase Global", "earnings_date": "", "sector": "Financial", "market_cap_category": "large", "options_available": True},
        {"symbol": "TSLA", "name": "Tesla Inc.", "earnings_date": "", "sector": "Consumer", "market_cap_category": "large", "options_available": True},
        {"symbol": "AMD", "name": "Advanced Micro Devices", "earnings_date": "", "sector": "Technology", "market_cap_category": "large", "options_available": True},
        {"symbol": "SQ", "name": "Block Inc.", "earnings_date": "", "sector": "Financial", "market_cap_category": "large", "options_available": True},
    ]
    return stocks


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


def refresh_earnings_candidates(db: Session, language: str = "en") -> list[dict]:
    stocks = _discover_earnings_stocks(db, language)
    candidates = []
    for stock in stocks:
        try:
            candidates.append(_score_stock(stock, db))
        except Exception:
            continue
    candidates.sort(key=lambda r: r["research_score"], reverse=True)
    with _EARNINGS_LOCK:
        _EARNINGS_CACHE[language] = (time.monotonic() + 172800, candidates)
    return candidates


def get_earnings_candidates(language: str = "en") -> list[dict]:
    with _EARNINGS_LOCK:
        entry = _EARNINGS_CACHE.get(language)
        if entry and entry[0] > time.monotonic():
            return entry[1]
    return []


def force_refresh_earnings(db: Session, language: str = "en") -> list[dict]:
    return refresh_earnings_candidates(db, language)
