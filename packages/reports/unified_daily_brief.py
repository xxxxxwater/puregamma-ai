"""Unified daily brief: one shared template-rendered brief for all users.

Non-LLM, deterministic rendering so daily output is stable and predictable.
Each section degrades independently: if a data source is unavailable the
section is skipped instead of blocking the whole brief. Output is clipped to
~200 characters of content and hard-capped for iMessage delivery.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from packages.data.earnings_calendar import upcoming_earnings
from packages.data.macro_calendar import events_for
from packages.data.trending import top_trending
from packages.database.models import MarketSnapshot, SharedMarketIntelligence, Signal
from packages.reports.templates import disclaimer_for

logger = logging.getLogger(__name__)

MAX_IMESSAGE_BYTES = 1500
_FULL_ANALYSIS_URL = "https://puregamma.ai"


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _macro_section(today: date, locale: str) -> str:
    try:
        events = events_for(today, locale)
    except Exception:
        logger.warning("unified_brief_macro_failed")
        events = []
    zh = locale == "zh"
    label = "宏观" if zh else "Macro"
    if not events:
        return f"{label}: " + ("今日无重大日程" if zh else "No major events today")
    return f"{label}: " + _clip("；".join(events) if zh else "; ".join(events), 40)


def _earnings_section(today: date, locale: str) -> str:
    try:
        items = upcoming_earnings(today, days=7, locale=locale)
    except Exception:
        logger.warning("unified_brief_earnings_failed")
        items = []
    if not items:
        return ""
    label = "美股财报(7天)" if locale == "zh" else "US earnings (7d)"
    return f"{label}: " + _clip("；".join(items) if locale == "zh" else "; ".join(items), 52)


def _trending_section(db: Session, locale: str) -> str:
    zh = locale == "zh"
    try:
        # Shared brief goes to every plan, so it only uses sources available to
        # all tiers. Plan-restricted sources (X/Twitter on Max+) are included
        # in the per-user report instead.
        items = top_trending(db, hours=24, limit=3, providers=("rss",))
    except Exception:
        logger.warning("unified_brief_trending_failed")
        items = []
    if not items:
        return ""
    label = "热议" if zh else "Trending"
    body = ("；" if zh else "; ").join(f"{item['symbol']}×{item['mentions']}" for item in items)
    return f"{label}: " + _clip(body, 36)


def _crypto_section(db: Session, locale: str) -> str:
    zh = locale == "zh"
    label = "加密" if zh else "Crypto"
    try:
        intelligence = (
            db.query(SharedMarketIntelligence)
            .order_by(SharedMarketIntelligence.created_at.desc())
            .first()
        )
        quotes: list[str] = []
        for asset in ("BTC", "ETH"):
            row = (
                db.query(MarketSnapshot)
                .filter(MarketSnapshot.asset_id == asset)
                .order_by(MarketSnapshot.timestamp.desc())
                .first()
            )
            if row and row.price:
                quotes.append(f"{asset} ${row.price:,.0f}")
        regime = (intelligence.market_regime if intelligence else "") or ("数据同步中" if zh else "Syncing")
        parts = [_clip(regime, 24), *quotes]
        return f"{label}: " + " · ".join(parts)[:60]
    except Exception:
        logger.warning("unified_brief_crypto_failed")
        return f"{label}: " + ("数据暂不可用" if zh else "Data temporarily unavailable")


def _signals_section(db: Session, locale: str) -> str:
    zh = locale == "zh"
    label = "信号" if zh else "Signals"
    try:
        rows = db.query(Signal).order_by(Signal.created_at.desc()).limit(2).all()
    except Exception:
        logger.warning("unified_brief_signals_failed")
        rows = []
    if not rows:
        return f"{label}: " + ("暂无新信号" if zh else "No new signals")
    items = [f"{row.asset} {row.direction} · {_clip(row.thesis, 28)}" for row in rows]
    return f"{label}: " + _clip("；".join(items) if zh else "; ".join(items), 60)


def render_unified_brief(db: Session, today: date, locale: str) -> str:
    zh = locale == "zh"
    header = f"PureGamma {'每日简报' if zh else 'Daily Brief'} · {today.strftime('%m-%d')}"
    sections = [
        _macro_section(today, locale),
        _earnings_section(today, locale),
        _crypto_section(db, locale),
        _trending_section(db, locale),
        _signals_section(db, locale),
    ]
    body = "\n".join(section for section in sections if section)
    cta = ("全文" if zh else "Full analysis") + f" → {_FULL_ANALYSIS_URL}"
    return f"{header}\n{body}\n{cta}"


def _enforce_imessage_cap(text: str) -> str:
    """Hard-cap the payload so it always fits one iMessage bubble (~1600 bytes)."""
    if len(text.encode("utf-8")) <= MAX_IMESSAGE_BYTES:
        return text
    encoded = text.encode("utf-8")[: MAX_IMESSAGE_BYTES - 1]
    while True:
        try:
            trimmed = encoded.decode("utf-8")
            break
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return trimmed.rstrip() + "…"


def generate_unified_daily_brief(db: Session, locale: str = "en", today: date | None = None) -> str:
    """Render the shared brief for one locale; always returns sendable text."""
    today = today or date.today()
    try:
        body = render_unified_brief(db, today, locale)
    except Exception:
        logger.exception("unified_brief_render_failed")
        body = (
            f"PureGamma 每日简报 · {today.strftime('%m-%d')}\n数据同步中，请稍后查看在线版本。\n全文 → {_FULL_ANALYSIS_URL}"
            if locale == "zh"
            else f"PureGamma Daily Brief · {today.strftime('%m-%d')}\nData is syncing; please check the online version shortly.\nFull analysis → {_FULL_ANALYSIS_URL}"
        )
    return _enforce_imessage_cap(f"{body}\n\n{disclaimer_for(locale)}")
