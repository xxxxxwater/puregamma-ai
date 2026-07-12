from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from apps.api.services.entitlement_service import get_user_entitlement
from apps.api.services.daily_brief_service import gather_context
from packages.database.models import DailyBriefPreference, NormalizedDocument, NotificationDelivery, Report, Signal, User, UserPreference
from packages.reports.templates import disclaimer_for


CHANNELS = {"email", "telegram", "imessage"}


def next_delivery(timezone_name: str, local_time: str, now: datetime | None = None) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("INVALID_TIMEZONE") from exc
    try:
        hour, minute = (int(value) for value in local_time.split(":", 1))
        target_time = time(hour=hour, minute=minute)
    except (ValueError, TypeError) as exc:
        raise ValueError("INVALID_LOCAL_TIME") from exc
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local_now = now_utc.astimezone(zone)
    candidate = datetime.combine(local_now.date(), target_time, tzinfo=zone)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def _recipient(user: User, channel: str) -> str | None:
    preference: UserPreference | None = user.preference
    if not preference:
        return None
    return {"email": preference.email_recipient or user.email, "telegram": preference.telegram_chat_id, "imessage": preference.imessage_recipient}.get(channel)


def get_or_create_preference(db: Session, user: User) -> DailyBriefPreference:
    row = db.get(DailyBriefPreference, user.id)
    if row:
        return row
    locale = user.preference.locale if user.preference else "en"
    row = DailyBriefPreference(user_id=user.id, locale=locale, recipient=_recipient(user, "email"))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_preference(db: Session, user: User, payload: dict) -> DailyBriefPreference:
    row = get_or_create_preference(db, user)
    channel = str(payload.get("channel", row.channel)).lower()
    if channel not in CHANNELS:
        raise ValueError("UNSUPPORTED_CHANNEL")
    entitlement = get_user_entitlement(db, user.id)
    if channel not in entitlement["notification_channels"]:
        raise PermissionError("CHANNEL_ENTITLEMENT_DENIED")
    timezone_name = str(payload.get("timezone", row.timezone))
    local_time = str(payload.get("local_time", row.local_time))
    scheduled = next_delivery(timezone_name, local_time)
    for key in ("enabled", "include_portfolio", "include_market", "include_signals", "include_risk", "include_sentiment"):
        if key in payload:
            setattr(row, key, bool(payload[key]))
    row.timezone = timezone_name
    row.local_time = local_time
    row.channel = channel
    row.locale = "zh" if payload.get("locale", row.locale) == "zh" else "en"
    row.quiet_hours = payload.get("quiet_hours", row.quiet_hours or {})
    row.max_length = max(280, min(3000, int(payload.get("max_length", row.max_length))))
    row.recipient = _recipient(user, channel)
    row.next_delivery_at = scheduled if row.enabled else None
    db.commit()
    db.refresh(row)
    return row


def serialize_preference(row: DailyBriefPreference) -> dict:
    return {"enabled": row.enabled, "timezone": row.timezone, "local_time": row.local_time, "channel": row.channel, "locale": row.locale, "include_portfolio": row.include_portfolio, "include_market": row.include_market, "include_signals": row.include_signals, "include_risk": row.include_risk, "include_sentiment": row.include_sentiment, "quiet_hours": row.quiet_hours or {}, "max_length": row.max_length, "next_delivery_at": row.next_delivery_at.isoformat() if row.next_delivery_at else None, "recipient": row.recipient, "recipient_verified_at": row.recipient_verified_at.isoformat() if row.recipient_verified_at else None}


def delivery_history(db: Session, user_id: str, channel: str | None = None) -> list[NotificationDelivery]:
    query = db.query(NotificationDelivery).filter(NotificationDelivery.user_id == user_id)
    if channel:
        query = query.filter(NotificationDelivery.channel == channel)
    return query.order_by(NotificationDelivery.created_at.desc()).limit(100).all()


def render_daily_brief_delivery(db: Session, preference: DailyBriefPreference, report: Report) -> str:
    context = gather_context(db, preference.user_id, preference.locale)
    zh = preference.locale == "zh"
    lines = ["PureGamma AI 每日简报" if zh else "PureGamma AI Daily Brief"]
    if preference.include_market:
        lines.extend(["", "市场" if zh else "Market", f"{context['market_regime']} · {context['market_data_as_of']}"])
        if context["quotes"]:
            lines.append(" · ".join(f"{item['symbol']} ${item['price']:,.2f}" for item in context["quotes"][:5]))
    if preference.include_portfolio:
        portfolio = context["portfolio"]
        lines.extend(["", "组合" if zh else "Portfolio"])
        if portfolio["connected"]:
            lines.append((f"NAV ${portfolio['total_nav']:,.2f} · 当日 ${portfolio['daily_change']:,.2f}" if zh else f"NAV ${portfolio['total_nav']:,.2f} · daily ${portfolio['daily_change']:,.2f}"))
            lines.append(" · ".join(f"{item['symbol']} {item['weight']:.1%}" for item in portfolio["top_holdings"][:5]))
        else:
            lines.append("尚未连接真实组合账户。" if zh else "No real portfolio account is connected.")
    if preference.include_signals:
        signals = db.query(Signal).order_by(Signal.created_at.desc()).limit(3).all()
        lines.extend(["", "信号" if zh else "Signals"])
        lines.extend(f"{row.asset} {row.direction} · {row.thesis[:120]}" for row in signals) if signals else lines.append("暂无新信号。" if zh else "No new signals.")
    if preference.include_risk:
        portfolio = context["portfolio"]
        notes = []
        if portfolio["concentration_hhi"] is not None:
            notes.append(("集中度" if zh else "Concentration") + f" HHI {portfolio['concentration_hhi']:.3f}")
        if context["market_stale"]:
            notes.append("市场数据已过期" if zh else "Market data is stale")
        if portfolio["stale"]:
            notes.append("组合数据已过期" if zh else "Portfolio data is stale")
        lines.extend(["", "风险" if zh else "Risk", " · ".join(notes) if notes else ("未发现新增数据完整性警告。" if zh else "No new data-integrity warning.")])
    if preference.include_sentiment:
        entitlement = get_user_entitlement(db, preference.user_id)
        allowed = set(entitlement["allowed_data_sources"])
        providers = [provider for provider in ("rss", "fintwit", "x-twitter", "bloomberg") if "all" in allowed or provider in allowed or (provider == "x-twitter" and "x" in allowed)]
        documents = db.query(NormalizedDocument).filter(NormalizedDocument.provider.in_(providers)).order_by(NormalizedDocument.published_at.desc(), NormalizedDocument.created_at.desc()).limit(3).all()
        lines.extend(["", "来源观点" if zh else "Source sentiment"])
        lines.extend(f"{row.source_name}: {(row.sentiment or {}).get('label', 'neutral')} · {row.title[:100]}" for row in documents) if documents else lines.append("当前没有可追溯的情绪来源。" if zh else "No traceable sentiment sources are available.")
    disclaimer = disclaimer_for(preference.locale)
    body = "\n".join(lines).rstrip()
    available = max(0, preference.max_length - len(disclaimer) - 2)
    return f"{body[:available].rstrip()}\n\n{disclaimer}"
