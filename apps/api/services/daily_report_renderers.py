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
import re
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.services import research_event_service
from apps.api.services.daily_brief_service import generate_daily_brief
from apps.api.services.market_intelligence_service import latest_or_create_intelligence
from apps.api.services.portfolio_service import portfolio_context
from packages.data.earnings_calendar import ProviderUnavailable, upcoming_confirmed_earnings
from packages.database.models import MarketEvent, ResearchAction, utcnow
from packages.reports.templates import disclaimer_for

REPORT_TYPES = ("crypto_daily", "us_daily", "week_ahead_events", "portfolio_daily")

# Only crypto_daily calls an LLM; everything else renders deterministically and
# is therefore generated without reserving credits.
LLM_REPORT_TYPES = frozenset({"crypto_daily"})

_US_QUOTE_KEY_ENV_VARS = ("MASSIVE_API_KEY", "FMP_API_KEY", "ALPHA_VANTAGE_API_KEY")

# A daily notification is a decision aid, not an exhaustive calendar export.
# Keep the headline list intentionally small and preserve the complete event
# set in the report metadata / calendar API for users who need to drill down.
_DAILY_EARNINGS_HIGHLIGHT_LIMIT = 5
_WEEKLY_EARNINGS_HIGHLIGHT_LIMIT = 3
_WEEKLY_MACRO_HIGHLIGHT_LIMIT = 5
_MARKET_CAP_MULTIPLIERS = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}


def _event_symbol(event: MarketEvent | dict) -> str:
    """Read the primary ticker without relying on the human title format."""
    assets = event.get("assets") if isinstance(event, dict) else event.assets
    if assets:
        return str(assets[0]).upper()
    title = event.get("title") if isinstance(event, dict) else event.title
    return str(title or "").split(" ", 1)[0].upper()


def _event_summary(event: MarketEvent | dict) -> str:
    return str(event.get("summary") if isinstance(event, dict) else event.summary or "")


def _earnings_summary_value(event: MarketEvent | dict, label: str) -> str | None:
    """Extract a provider-supplied earnings field from the stored summary.

    Research events predate structured earnings metadata, so this deliberately
    reads only the deterministic values written by ``research_event_service``.
    Unknown formats simply omit the value instead of guessing.
    """
    summary = _event_summary(event)
    if label == "eps":
        match = re.search(r"EPS forecast:\s*(.+?)(?=\.\s*Market cap:|\.\s*$|$)", summary, flags=re.IGNORECASE)
    elif label == "market_cap":
        match = re.search(r"Market cap:\s*(.+?)(?=\.\s*$|$)", summary, flags=re.IGNORECASE)
    elif label == "time":
        match = re.search(r"reports earnings on\s+\d{4}-\d{2}-\d{2}\s*\(([^)]+)\)", summary, flags=re.IGNORECASE)
    else:
        return None
    return match.group(1).strip() if match else None


def _market_cap_value(event: MarketEvent | dict) -> float:
    """Return a comparable disclosed market cap, or zero when unavailable."""
    raw = _earnings_summary_value(event, "market_cap")
    if not raw:
        return 0.0
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMBT])?", raw.replace(",", "").upper())
    if not match:
        return 0.0
    return float(match.group(1)) * _MARKET_CAP_MULTIPLIERS.get(match.group(2) or "", 1)


def _prioritised_earnings(events: list[MarketEvent | dict], limit: int) -> list[MarketEvent | dict]:
    """Pick liquid-relevance proxies first using Nasdaq's disclosed market cap."""
    return sorted(events, key=lambda event: (-_market_cap_value(event), _event_symbol(event)))[:limit]


def _earnings_time_label(raw: str | None, zh: bool) -> str | None:
    if not raw:
        return None
    value = raw.lower()
    if "after" in value:
        return "盘后" if zh else "after close"
    if "before" in value or "pre-market" in value:
        return "盘前" if zh else "before open"
    if "during" in value:
        return "盘中" if zh else "during session"
    if "not supplied" in value or "not available" in value:
        return None
    return raw


def _format_earnings_highlight(event: MarketEvent | dict, language: str) -> str:
    zh = language == "zh"
    fields = [_event_symbol(event)]
    time_label = _earnings_time_label(_earnings_summary_value(event, "time"), zh)
    eps = _earnings_summary_value(event, "eps")
    market_cap = _earnings_summary_value(event, "market_cap")
    if time_label:
        fields.append(time_label)
    if eps:
        fields.append((f"EPS预期 {eps}" if zh else f"EPS est. {eps}"))
    if market_cap:
        fields.append((f"市值 {market_cap}" if zh else f"market cap {market_cap}"))
    return "｜".join(fields)


def _earnings_day_summary(events: list[MarketEvent | dict], language: str, limit: int) -> list[str]:
    """Render a compact day card: top names plus an honest omitted count."""
    zh = language == "zh"
    if not events:
        return ["暂无已确认财报。" if zh else "No confirmed earnings."]
    highlighted = _prioritised_earnings(events, limit)
    lines = [f"- {_format_earnings_highlight(event, language)}" for event in highlighted]
    if len(events) > len(highlighted):
        lines.append(
            f"已确认 {len(events)} 家；仅展示按已披露市值排序的前 {len(highlighted)} 家，其余 {len(events) - len(highlighted)} 家见事件日历。"
            if zh
            else f"{len(events)} confirmed; showing the top {len(highlighted)} by disclosed market cap, with {len(events) - len(highlighted)} more in the event calendar."
        )
    return lines


def _live_confirmed_earnings(start_day: date, days: int) -> list[dict] | None:
    """Read the Nasdaq calendar at render time; never substitute old DB rows.

    Stored research events remain valuable for history and the event calendar,
    but a daily notification is a present-tense product.  ``None`` carries an
    explicit provider outage so the renderer can be honest rather than using a
    stale event as a fallback.
    """
    # Explicit offline/test mode must not make background jobs issue external
    # requests.  Rendering the unavailable state is preferable to pretending
    # that test fixtures are a live Nasdaq response.
    if os.getenv("ENABLE_MOCK_MARKET_DATA", "false").lower() == "true":
        return None
    try:
        rows = upcoming_confirmed_earnings(start_day, days=days, fresh=True)
    except ProviderUnavailable:
        return None

    events: list[dict] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        raw_day = str(row.get("as_of") or "")
        if not symbol:
            continue
        try:
            scheduled_for = datetime.combine(date.fromisoformat(raw_day), time.min, tzinfo=timezone.utc)
        except ValueError:
            continue
        name = str(row.get("name") or symbol).strip()
        time_label = str(row.get("time_label") or "").strip()
        eps_forecast = row.get("eps_forecast")
        market_cap = row.get("market_cap")
        summary = f"{name} ({symbol}) reports earnings on {raw_day} ({time_label or 'time not supplied'}). Confirmed via the Nasdaq earnings calendar."
        if eps_forecast:
            summary += f" EPS forecast: {eps_forecast}."
        if market_cap:
            summary += f" Market cap: {market_cap}."
        events.append(
            {
                "event_type": "earnings_confirmed",
                "title": f"{symbol} earnings confirmed for {raw_day}",
                "summary": summary,
                "assets": [symbol],
                "source_published_at": scheduled_for,
                "source_url": row.get("source_url"),
            }
        )
    return events


def _earnings_unavailable(language: str) -> list[str]:
    return [
        "实时 Nasdaq 财报日历暂不可用；不展示历史缓存结果。"
        if language == "zh"
        else "The live Nasdaq earnings calendar is unavailable; no historical cache is shown."
    ]


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


def _earnings_gamma_section(language: str) -> tuple[str, list[str]]:
    """Top-3 Long Gamma candidates during earnings season (deterministic)."""
    zh = language == "zh"
    try:
        from packages.options.earnings_gamma import get_earnings_candidates

        candidates = get_earnings_candidates("zh" if zh else "en")[:3]
    except Exception:
        candidates = []
    if not candidates:
        return "", []
    lines = [
        "## Long Gamma 候选（财报季 · 推荐 3 个）"
        if zh
        else "## Long Gamma candidates (earnings season · top 3)"
    ]
    assets: list[str] = []
    for candidate in candidates:
        symbol = str(candidate.get("symbol") or "").upper()
        name = str(candidate.get("name") or symbol)
        earnings_date = str(candidate.get("earnings_date") or "")
        score = candidate.get("research_score")
        rationale = "；".join(str(r) for r in (candidate.get("rationale") or [])[:2])
        if zh:
            lines.append(f"- {symbol}（{name}）：财报 {earnings_date}，研究评分 {score}，{rationale}。")
        else:
            lines.append(f"- {symbol} ({name}): earnings {earnings_date}, research score {score}, {rationale}.")
        if symbol:
            assets.append(symbol)
    return "\n".join(lines), assets


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
    earnings = _live_confirmed_earnings(local_date, days=2)
    macro = _scheduled_events(db, "macro_scheduled", today_start, three_days_out)
    today_earnings = [] if earnings is None else [event for event in earnings if (_as_utc(event.get("source_published_at")) or today_start) < tomorrow_start]
    tomorrow_earnings = [] if earnings is None else [event for event in earnings if (_as_utc(event.get("source_published_at")) or tomorrow_start) >= tomorrow_start]

    title = f"PureGamma 美股财报重点 · {local_date.isoformat()}" if zh else f"PureGamma US Earnings Focus · {local_date.isoformat()}"
    lines = [f"# {title}", ""]
    lines.append("## 今日重点财报" if zh else "## Today: earnings focus")
    lines.extend(_earnings_unavailable(language) if earnings is None else _earnings_day_summary(today_earnings, language, _DAILY_EARNINGS_HIGHLIGHT_LIMIT))
    lines.extend(["", "## 明日预告" if zh else "## Tomorrow: early view"])
    lines.extend(_earnings_unavailable(language) if earnings is None else _earnings_day_summary(tomorrow_earnings, language, _DAILY_EARNINGS_HIGHLIGHT_LIMIT))
    gamma_section, gamma_assets = _earnings_gamma_section(language)
    if gamma_section:
        lines.extend(["", gamma_section])
    lines.extend(["", "## 未来三日宏观" if zh else "## Macro: next three days"])
    if macro:
        for event in macro[:_WEEKLY_MACRO_HIGHLIGHT_LIMIT]:
            day = (_as_utc(event.source_published_at) or today_start).date().isoformat()
            label = event.title.split(" — ")[0]
            lines.append(f"- {day}: {label}")
        if len(macro) > _WEEKLY_MACRO_HIGHLIGHT_LIMIT:
            lines.append(
                f"另有 {len(macro) - _WEEKLY_MACRO_HIGHLIGHT_LIMIT} 项已排期宏观事件，见事件日历。"
                if zh
                else f"{len(macro) - _WEEKLY_MACRO_HIGHLIGHT_LIMIT} additional scheduled macro events are in the event calendar."
            )
    else:
        lines.append("未来 3 天没有已排期的宏观发布。" if zh else "No scheduled macro releases in the next 3 days.")
    lines.append("")
    as_of = utcnow().isoformat()
    source_note = (
        f"数据截至 {as_of}（UTC）。来源：本次直连 Nasdaq 财报日历与规则宏观日历。"
        if zh
        else f"As of {as_of} (UTC). Sources: this-render Nasdaq earnings calendar fetch and the rule-based macro calendar."
    )
    if not us_market_data_configured():
        source_note += " 未接入美股盘中行情，因此不展示涨跌幅。" if zh else " US cash-session quotes are not configured, so no intraday moves are shown."
    lines.append(source_note)
    lines.extend(["", disclaimer_for(language)])
    assets = sorted({str(asset).upper() for event in (earnings or []) for asset in (event.get("assets") or [])} | {asset for asset in gamma_assets if asset})
    return {"title": title, "content_markdown": "\n".join(lines), "assets": assets, "source_intelligence_id": None}


def _render_week_ahead_events(db: Session, user_id: str, language: str, local_date: date) -> dict:
    zh = language == "zh"
    payload = research_event_service.get_upcoming_events(db, days=7)
    earnings = _live_confirmed_earnings(local_date, days=7)
    title = f"未来一周事件 · {local_date.isoformat()}" if zh else f"Week Ahead: Scheduled Events · {local_date.isoformat()}"
    lines = [f"# {title}", ""]
    by_day: dict[str, list[dict]] = {}
    for event in earnings or []:
        published = (_as_utc(event.get("source_published_at")) or datetime.now(timezone.utc)).date().isoformat()
        by_day.setdefault(published, []).append(event)
    lines.append("## 财报节奏" if zh else "## Earnings cadence")
    if earnings is None:
        lines.extend(_earnings_unavailable(language))
    elif not by_day:
        lines.append("未来 7 天暂无已确认财报。" if zh else "No confirmed earnings in the next 7 days.")
    else:
        for day in sorted(by_day):
            day_earnings = by_day[day]
            highlighted = _prioritised_earnings(day_earnings, _WEEKLY_EARNINGS_HIGHLIGHT_LIMIT)
            symbols = "、".join(_event_symbol(event) for event in highlighted) if zh else ", ".join(_event_symbol(event) for event in highlighted)
            suffix = (
                f"等 {len(day_earnings)} 家" if len(day_earnings) > len(highlighted) else f"共 {len(day_earnings)} 家"
            ) if zh else (
                f" + {len(day_earnings) - len(highlighted)} more" if len(day_earnings) > len(highlighted) else f" · {len(day_earnings)} confirmed"
            )
            lines.append(f"- {day}：{symbols}（{suffix}）" if zh else f"- {day}: {symbols}{suffix}")

    macro_events = [event for event in (payload.get("events") or []) if event.get("event_type") == "macro_scheduled"]
    if macro_events:
        lines.extend(["", "## 关键宏观" if zh else "## Key macro"])
        for event in macro_events[:_WEEKLY_MACRO_HIGHLIGHT_LIMIT]:
            published = ((event.get("source") or {}).get("published_at") or "")[:10]
            label = str(event.get("title") or "").split(" — ")[0]
            lines.append(f"- {published}: {label}")
        if len(macro_events) > _WEEKLY_MACRO_HIGHLIGHT_LIMIT:
            lines.append(
                f"其余 {len(macro_events) - _WEEKLY_MACRO_HIGHLIGHT_LIMIT} 项见事件日历。"
                if zh
                else f"{len(macro_events) - _WEEKLY_MACRO_HIGHLIGHT_LIMIT} more are in the event calendar."
            )
    lines.append("")
    as_of = payload.get("as_of") or utcnow().isoformat()
    lines.append(
        f"数据截至 {as_of}（UTC）。来源：本次直连 Nasdaq 财报日历 + 规则宏观日历。"
        if zh
        else f"As of {as_of} (UTC). Sources: this-render Nasdaq earnings calendar fetch + rule-based macro calendar."
    )
    lines.extend(["", disclaimer_for(language)])
    assets = sorted({str(asset).upper() for event in (earnings or []) for asset in (event.get("assets") or [])})
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
