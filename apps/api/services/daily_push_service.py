from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from apps.api.services.entitlement_service import get_user_entitlement
from packages.database.models import DailyBriefPreference, NotificationDelivery, User, UserPreference


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
