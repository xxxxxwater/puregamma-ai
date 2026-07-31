from __future__ import annotations

from sqlalchemy.orm import Session

from packages.database.models import NotificationDelivery
from packages.notifications.dispatcher import NotificationDispatcher


def send_notification(db: Session, user_id: str, channel: str, message: str, metadata: dict | None = None) -> NotificationDelivery:
    return NotificationDispatcher().send(db, user_id, channel, message, metadata)


def serialize_delivery(delivery: NotificationDelivery) -> dict:
    return {
        "id": delivery.id,
        "user_id": delivery.user_id,
        "channel": delivery.channel,
        "recipient": delivery.recipient,
        "payload": delivery.payload,
        "locale": delivery.locale,
        "status": delivery.status,
        "provider_response": delivery.provider_response,
        "idempotency_key": delivery.idempotency_key,
        "retry_count": delivery.retry_count,
        "attempt_count": delivery.attempt_count,
        "last_attempt_at": delivery.last_attempt_at.isoformat() if delivery.last_attempt_at else None,
        "next_retry_at": delivery.next_retry_at.isoformat() if delivery.next_retry_at else None,
        "last_error": delivery.last_error,
        "created_at": delivery.created_at.isoformat(),
        "sent_at": delivery.sent_at.isoformat() if delivery.sent_at else None,
    }
