from __future__ import annotations

import hashlib
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.i18n import normalize_locale
from apps.api.services.credit_service import (
    InsufficientCreditsError,
    consume_credits,
    refund_credits,
)
from apps.api.services.entitlement_service import EntitlementDeniedError, assert_action_allowed
from packages.billing.credits import cost_for
from packages.database.models import NotificationDelivery, User, UserPreference, utcnow
from packages.notifications.email import EmailProvider
from packages.notifications.imessage.macos_relay_client import MacOSIMessageRelayClient
from packages.notifications.imessage.mock_provider import MockIMessageProvider
from packages.notifications.slack import SlackProvider
from packages.notifications.telegram import TelegramProvider
from apps.api.services.imessage_verification_service import normalize_e164


CHANNEL_ACTION = {
    "telegram": "telegram_alert",
    "slack": "slack_alert",
    "email": "email_alert",
    "imessage": "imessage_alert",
}


class NotificationDispatcher:
    def __init__(self):
        self.settings = get_settings()

    def _provider(self, channel: str):
        if channel == "telegram":
            return TelegramProvider()
        if channel == "slack":
            return SlackProvider()
        if channel == "email":
            return EmailProvider()
        if channel == "imessage":
            return (
                MacOSIMessageRelayClient()
                if self.settings.imessage_provider == "macos_relay"
                else MockIMessageProvider()
            )
        raise ValueError(f"Unsupported channel: {channel}")

    def _recipient(
        self, pref: UserPreference | None, channel: str, metadata: dict
    ) -> str | None:
        if not pref:
            return None
        return {
            "telegram": pref.telegram_chat_id,
            "slack": pref.slack_webhook_url,
            "email": pref.email_recipient,
            "imessage": pref.imessage_recipient,
        }.get(channel)

    def _key(self, user_id: str, channel: str, message: str, metadata: dict) -> str:
        explicit = metadata.get("idempotency_key")
        if explicit:
            return explicit
        digest = hashlib.sha256(f"{user_id}:{channel}:{message}".encode()).hexdigest()[
            :32
        ]
        return f"pg_{digest}"

    def _imessage_count_today(self, db: Session, user_id: str) -> int:
        start = datetime.combine(
            datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc
        )
        return (
            db.query(NotificationDelivery)
            .filter(
                NotificationDelivery.user_id == user_id,
                NotificationDelivery.channel == "imessage",
                NotificationDelivery.status == "sent",
                NotificationDelivery.created_at >= start,
            )
            .count()
        )

    def _create_delivery(
        self,
        db: Session,
        user_id: str,
        channel: str,
        recipient: str | None,
        message: str,
        idempotency_key: str,
        status: str,
        provider_response: dict | None = None,
        locale: str = "en",
    ) -> NotificationDelivery:
        delivery = NotificationDelivery(
            user_id=user_id,
            channel=channel,
            recipient=recipient,
            payload={"message": message},
            locale=locale,
            status=status,
            provider_response=provider_response or {},
            idempotency_key=idempotency_key,
            sent_at=utcnow() if status == "sent" else None,
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        return delivery

    def send(
        self,
        db: Session,
        user_id: str,
        channel: str,
        message: str,
        metadata: dict | None = None,
    ) -> NotificationDelivery:
        metadata = metadata or {}
        user = db.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        idempotency_key = self._key(user_id, channel, message, metadata)
        existing = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing and existing.status in {"sent", "skipped", "failed", "failed_permanent"}:
            return existing
        if existing and existing.status == "failed_retryable" and existing.next_retry_at:
            retry_at = existing.next_retry_at
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            if retry_at > utcnow():
                return existing
        pref = user.preference
        locale = normalize_locale(
            metadata.get("locale") or getattr(pref, "locale", None)
        )
        recipient = self._recipient(pref, channel, metadata)
        if not recipient:
            return self._create_delivery(
                db,
                user_id,
                channel,
                recipient,
                message,
                idempotency_key,
                "skipped",
                {"reason": "missing_recipient"},
                locale=locale,
            )
        if self.settings.app_environment.lower() == "production":
            configured = {
                "telegram": bool(self.settings.telegram_bot_token),
                "slack": bool(
                    self.settings.slack_webhook_url
                    or getattr(pref, "slack_webhook_url", None)
                ),
                "email": bool(self.settings.smtp_host),
                "imessage": self.settings.imessage_provider == "macos_relay"
                and bool(self.settings.imessage_relay_secret),
            }.get(channel, False)
            if not configured:
                return self._create_delivery(
                    db,
                    user_id,
                    channel,
                    recipient,
                    message,
                    idempotency_key,
                    "failed",
                    {"reason": "provider_not_configured"},
                    locale=locale,
                )
        if channel == "imessage":
            try:
                recipient = normalize_e164(recipient)
            except ValueError:
                return self._create_delivery(db, user_id, channel, recipient, message, idempotency_key, "skipped", {"reason": "invalid_recipient"}, locale=locale)
            if self.settings.imessage_provider == "macos_relay" and (not pref.imessage_recipient_verified_at or pref.imessage_recipient != recipient):
                return self._create_delivery(db, user_id, channel, recipient, message, idempotency_key, "skipped", {"reason": "recipient_unverified"}, locale=locale)
            if len(message) > self.settings.imessage_max_message_length:
                return self._create_delivery(
                    db,
                    user_id,
                    channel,
                    recipient,
                    message,
                    idempotency_key,
                    "skipped",
                    {"reason": "message_too_long"},
                    locale=locale,
                )
            if self._imessage_count_today(db, user_id) >= self.settings.imessage_rate_limit_per_user_per_day:
                return self._create_delivery(
                    db,
                    user_id,
                    channel,
                    recipient,
                    message,
                    idempotency_key,
                    "skipped",
                    {"reason": "daily_rate_limit"},
                    locale=locale,
                )
        action = CHANNEL_ACTION[channel]
        attempt = (existing.attempt_count if existing else 0) + 1
        try:
            assert_action_allowed(db, user_id, action)
            consume_credits(
                db,
                user_id,
                action,
                cost_for(action),
                {"channel": channel, "idempotency_key": idempotency_key},
                idempotency_key=f"notification-charge:{idempotency_key}:{attempt}",
            )
            db.commit()
        except (InsufficientCreditsError, EntitlementDeniedError) as exc:
            db.rollback()
            return self._create_delivery(
                db,
                user_id,
                channel,
                recipient,
                message,
                idempotency_key,
                "skipped",
                {
                    "reason": "insufficient_credits"
                    if isinstance(exc, InsufficientCreditsError)
                    else "entitlement_denied"
                },
                locale=locale,
            )
        provider = self._provider(channel)
        result = provider.send(recipient, message, idempotency_key)
        permanent = result.response.get("status") in {"unsupported_os", "invalid_recipient", "message_too_long", "missing_applescript"}
        status = "sent" if result.ok else ("failed_permanent" if permanent else "failed_retryable") if channel == "imessage" else "failed"
        if not result.ok:
            refund_credits(
                db,
                user_id,
                action,
                cost_for(action),
                {
                    "channel": channel,
                    "idempotency_key": idempotency_key,
                    "reason": "provider_failure",
                },
                idempotency_key=f"notification-refund:{idempotency_key}:{attempt}",
            )
            db.commit()
        retry_delays = (1, 5, 30)
        next_retry_at = utcnow() + timedelta(minutes=retry_delays[min(attempt - 1, 2)]) if status == "failed_retryable" and attempt < 3 else None
        if status == "failed_retryable" and attempt >= 3:
            status = "failed_permanent"
        if existing:
            existing.status = status
            existing.provider_response = result.response
            existing.attempt_count = attempt
            existing.retry_count = max(0, attempt - 1)
            existing.last_attempt_at = utcnow()
            existing.next_retry_at = next_retry_at
            existing.last_error = None if result.ok else "provider_failed"
            existing.sent_at = utcnow() if result.ok else None
            db.commit()
            db.refresh(existing)
            return existing
        delivery = self._create_delivery(db, user_id, channel, recipient, message, idempotency_key, status, result.response, locale=locale)
        delivery.attempt_count = attempt
        delivery.last_attempt_at = utcnow()
        delivery.next_retry_at = next_retry_at
        delivery.last_error = None if result.ok else "provider_failed"
        db.commit()
        db.refresh(delivery)
        return delivery
