"""Typed daily report renderers for the unified daily report orchestrator (P0-8).

One renderer per schedulable report type:

* ``crypto_daily``       — the existing LLM brief (shared intelligence + portfolio
                           context). This is the ONLY renderer that calls an LLM
                           and therefore the only one that is billed.
* ``us_daily``           — deterministic markdown from stored confirmed-earnings
                           and macro-scheduled MarketEvents (research pipeline).
                           No US cash-session numbers are ever fabricated: when no
                           US equity quote source is configured a clearly labeled
                           health note is rendered instead.
* ``week_ahead_events``  — deterministic markdown from
                           ``research_event_service.get_upcoming_events(db, days=7)``
                           grouped by day.
* ``portfolio_daily``    — deterministic sections from
                           ``portfolio_service.portfolio_context`` plus open
                           ResearchAction rows. Deliberately NON-LLM so scheduled
                           portfolio digests never consume LLM credits; users who
                           want the LLM portfolio narrative still get it inside
                           ``crypto_daily`` (which already includes the
                           portfolio-aware branch of ``generate_daily_brief``).

All renderers are bilingual (en/zh), include as-of and source notes, and never
invent numbers.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.services import research_event_service
from apps.api.services.daily_brief_service import generate_daily_brief
from apps.api.services.market_intelligence_service import latest_or_create_intelligence
from apps.api.services.portfolio_service import portfolio_context
from packages.database.models import MarketEvent, ResearchAction, utcnow
from packages.reports.templates import disclaimer_for

REPORT_TYPES = ("crypto_daily", "us_daily", "week_ahead_events", "portfolio_daily")

# Only crypto_daily calls an LLM; everything else renders deterministically and
# is therefore generated without reserving credits.
LLM_REPORT_TYPES = frozenset({"crypto_daily"})

_US_QUOTE_KEY_ENV_VARS = ("MASSIVE_API_KEY", "FMP_API_KEY", "ALPHA_VANTAGE_API_KEY")


def us_market_data_configured() -> bool:
    """Boolean env presence check for a US equity quote source.

    Never reads, logs, or returns key material — only whether a source exists.
    The mock market-data provider is a test fixture, not a real US source.
    """
    if os.getenv("NASDAQ_DATA_LINK_BASE_URL") and os.getenv("NASDAQ_DATA_LINK_CLIENT_ID") and os.getenv("NASDAQ_DATA_LINK_CLIENT_SECRET"):
        return True
    return any(os.getenv(name) for name in _US_QUOTE_KEY_ENV_VARS)


def _day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _scheduled_events(db: Session, event_type: str, start: datetime, end: datetime) -> list[MarketEvent]:
    return (
        db.query(MarketEvent)
        .filter(
            MarketEvent.status == "active",
            MarketEvent.event_type == event_type,
            MarketEvent.source_published_at.isnot(None),
            MarketEvent.source_published_at >= start,
            MarketEvent.source_published_at < end,
        )
        .order_by(MarketEvent.source_published_at.asc(), MarketEvent.title.asc())
        .all()
    )


def _render_crypto_daily(db: Session, user_id: str, language: str, local_date: date) -> dict:
    content = generate_daily_brief(db, user_id, language)
    intelligence = latest_or_create_intelligence(db)
    disclaimer = disclaimer_for(language)
    if disclaimer not in content:
        content = f"{content.rstrip()}\n\n{disclaimer}"
    return {
        "title": "PureGamma 每日简报" if language == "zh" else "PureGamma Daily Brief",
        "content_markdown": content,
        "assets": list(intelligence.assets or []),
        "source_intelligence_id": intelligence.id,
    }


def _render_us_daily(db: Session, user_id: str, language: str, local_date: date) -> dict:
    zh = language == "zh"
    today_start, tomorrow_start = _day_bounds_utc(local_date)
    day_after, three_days_out = tomorrow_start + timedelta(days=1), today_start + timedelta(days=3)
    earnings = _scheduled_events(db, "earnings_confirmed", today_start, day_after)
    macro = _scheduled_events(db, "macro_scheduled", today_start, three_days_out)

    title = f"PureGamma 美股日报 · {local_date.isoformat()}" if zh else f"PureGamma US Daily · {local_date.isoformat()}"
    lines = [f"# {title}", ""]
    lines.append("## 财报（今天与明天，已确认）" if zh else "## Confirmed earnings (today & tomorrow)")
    if earnings:
        for event in earnings:
            lines.append(f"- {event.title}")
    else:
        lines.append("今明两天没有已确认的财报记录。" if zh else "No confirmed earnings recorded for today or tomorrow.")
    lines.append("")
    lines.append("## 宏观日程（未来 3 天）" if zh else "## Macro schedule (next 3 days)")
    if macro:
        for event in macro:
            day = (_as_utc(event.source_published_at) or today_start).date().isoformat()
            label = event.title.split(" — ")[0]
            lines.append(f"- {day}: {label}")
    else:
        lines.append("未来 3 天没有已排期的宏观发布。" if zh else "No scheduled macro releases in the next 3 days.")
    lines.append("")
    lines.append("## 美股盘中数据" if zh else "## US cash session")
    if us_market_data_configured():
        lines.append("美股行情数据源：已配置。" if zh else "US market data source: configured.")
    else:
        lines.append(
            "美股盘中数据：不可用 — 未配置美股行情数据源。"
            if zh
            else "US cash-session data: unavailable — no US market data source configured."
        )
    lines.append("")
    as_of = utcnow().isoformat()
    lines.append(
        f"数据截至 {as_of}（UTC）。来源：Nasdaq 财报日历与规则宏观日历（经研究事件管线入库）；未配置数据源时绝不编造行情数字。"
        if zh
        else f"As of {as_of} (UTC). Sources: Nasdaq earnings calendar and the rule-based macro calendar via the research event pipeline; no quotes are fabricated when no source is configured."
    )
    lines.extend(["", disclaimer_for(language)])
    assets = sorted({str(asset).upper() for event in earnings for asset in (event.assets or [])})
    return {"title": title, "content_markdown": "\n".join(lines), "assets": assets, "source_intelligence_id": None}


def _render_week_ahead_events(db: Session, user_id: str, language: str, local_date: date) -> dict:
    zh = language == "zh"
    payload = research_event_service.get_upcoming_events(db, days=7)
    title = f"未来一周事件 · {local_date.isoformat()}" if zh else f"Week Ahead: Scheduled Events · {local_date.isoformat()}"
    lines = [f"# {title}", ""]
    by_day: dict[str, list[dict]] = {}
    for event in payload.get("events") or []:
        published = ((event.get("source") or {}).get("published_at") or "")[:10] or ("日期未知" if zh else "date unknown")
        by_day.setdefault(published, []).append(event)
    if not by_day:
        lines.append("未来 7 天没有已排期的财报或宏观事件。" if zh else "No scheduled earnings or macro events in the next 7 days.")
    for day in sorted(by_day):
        lines.append(f"## {day}")
        for event in by_day[day]:
            is_earnings = event.get("event_type") == "earnings_confirmed"
            kind = ("财报" if is_earnings else "宏观") if zh else ("earnings" if is_earnings else "macro")
            lines.append(f"- [{kind}] {event.get('title')}")
        lines.append("")
    as_of = payload.get("as_of") or utcnow().isoformat()
    lines.append(
        f"数据截至 {as_of}（UTC）。来源：研究事件管线（Nasdaq 已确认财报 + 规则宏观日历）。"
        if zh
        else f"As of {as_of} (UTC). Source: research event pipeline (Nasdaq confirmed earnings + rule-based macro calendar)."
    )
    lines.extend(["", disclaimer_for(language)])
    assets = sorted({str(asset).upper() for event in (payload.get("events") or []) for asset in (event.get("assets") or [])})
    return {"title": title, "content_markdown": "\n".join(lines).strip(), "assets": assets, "source_intelligence_id": None}


def _render_portfolio_daily(db: Session, user_id: str, language: str, local_date: date) -> dict:
    zh = language == "zh"
    context = portfolio_context(db, user_id)
    title = f"组合日报 · {local_date.isoformat()}" if zh else f"Portfolio Daily · {local_date.isoformat()}"
    lines = [f"# {title}", ""]
    if context.get("connected"):
        lines.append("## 组合概览" if zh else "## Portfolio overview")
        nav = context.get("total_nav")
        daily_change = context.get("daily_change")
        daily_change_pct = context.get("daily_change_pct")
        if nav is not None:
            change_text = ""
            if daily_change is not None:
                pct = f" ({daily_change_pct:+.2f}%)" if daily_change_pct is not None else ""
                change_text = (f"；24h 变化 ${daily_change:+,.2f}{pct}" if zh else f"; 24h change ${daily_change:+,.2f}{pct}")
            lines.append((f"净值 NAV：${nav:,.2f}{change_text}。" if zh else f"NAV: ${nav:,.2f}{change_text}."))
        holdings = context.get("top_holdings") or []
        if holdings:
            lines.append("")
            lines.append("## 主要持仓" if zh else "## Top holdings")
            for item in holdings[:8]:
                weight = item.get("weight")
                weight_text = f" {weight:.1%}" if weight is not None else ""
                lines.append(f"- {item.get('symbol')}{weight_text}")
        concentration = context.get("concentration_hhi")
        if concentration is not None:
            lines.append("")
            lines.append((f"集中度 HHI：{concentration:.3f}。" if zh else f"Concentration HHI: {concentration:.3f}."))
        data_as_of = context.get("data_as_of")
        if context.get("stale"):
            lines.append("⚠ 组合数据已过期，请以最新同步为准。" if zh else "⚠ Portfolio data is stale; rely on the latest sync.")
        if data_as_of:
            lines.append((f"组合数据时间：{data_as_of}。" if zh else f"Portfolio data as of: {data_as_of}."))
    else:
        lines.append("## 连接账户" if zh else "## Connect accounts")
        lines.append(
            "尚未连接真实组合账户。连接券商或钱包后，本报告将展示净值、24 小时变化、主要持仓与集中度；未连接前不展示任何估算持仓或 NAV。"
            if zh
            else "No real portfolio account is connected. Link a brokerage or wallet to see NAV, 24h change, top holdings, and concentration here; until then no estimated holdings or NAV are shown."
        )
        for note in context.get("missing_data") or []:
            lines.append(f"- {note}")
    actions = (
        db.query(ResearchAction)
        .filter(ResearchAction.status == "open", (ResearchAction.user_id == user_id) | (ResearchAction.user_id.is_(None)))
        .order_by(ResearchAction.created_at.desc())
        .limit(5)
        .all()
    )
    lines.append("")
    lines.append("## 建议的下一步" if zh else "## Suggested next steps")
    if actions:
        for action in actions:
            lines.append(f"- {action.title}")
    else:
        lines.append("当前没有待处理的研究行动。" if zh else "No open research actions right now.")
    lines.append("")
    as_of = utcnow().isoformat()
    lines.append(
        f"数据截至 {as_of}（UTC）。来源：已同步的账户快照与研究事件管线；本报告不使用 LLM，不消耗 LLM 额度。"
        if zh
        else f"As of {as_of} (UTC). Sources: synchronized account snapshots and the research event pipeline; this report is deterministic and uses no LLM credits."
    )
    lines.extend(["", disclaimer_for(language)])
    assets = [str(item.get("symbol")).upper() for item in (context.get("top_holdings") or [])[:8] if item.get("symbol")]
    return {"title": title, "content_markdown": "\n".join(lines), "assets": assets, "source_intelligence_id": None}


_RENDERERS = {
    "crypto_daily": _render_crypto_daily,
    "us_daily": _render_us_daily,
    "week_ahead_events": _render_week_ahead_events,
    "portfolio_daily": _render_portfolio_daily,
}


def render_daily_report(db: Session, user_id: str, report_type: str, language: str, local_date: date | None = None) -> dict:
    """Render one typed daily report → {title, content_markdown, assets, source_intelligence_id}."""
    renderer = _RENDERERS.get(report_type)
    if renderer is None:
        raise ValueError(f"UNSUPPORTED_REPORT_TYPE:{report_type}")
    return renderer(db, user_id, language, local_date or utcnow().date())
