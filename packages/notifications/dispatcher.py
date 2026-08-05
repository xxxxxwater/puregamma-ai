from __future__ import annotations

import hashlib
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.i18n import normalize_locale
from apps.api.services.credit_service import (
    InsufficientCreditsError,
    quote_task,
    refund_task,
    reserve_task,
    settle_task,
)
from apps.api.services.entitlement_service import EntitlementDeniedError, assert_action_allowed
from packages.billing.budgets import AutomationBudgetExceeded
from packages.database.models import NotificationDelivery, PushDevice, User, UserPreference, utcnow
from packages.notifications.apns import APNsProvider
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
    "push": "push_alert",
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
            if self.settings.imessage_provider == "macos_relay":
                return MacOSIMessageRelayClient()
            if self.settings.app_environment.lower() != "production" and self.settings.imessage_provider == "mock":
                return MockIMessageProvider()
            raise RuntimeError("IMESSAGE_PROVIDER_UNAVAILABLE")
        raise ValueError(f"Unsupported channel: {channel}")

    def _recipient(
        self, user_id: str, pref: UserPreference | None, channel: str, metadata: dict
    ) -> str | None:
        if channel in {"push", "web"}:
            return user_id
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
        if existing and existing.status in {
            "sent",
            "skipped",
            "skipped_entitlement",
            "skipped_insufficient_credits",
            "skipped_budget",
            "failed",
            "failed_permanent",
        }:
            return existing
        if existing and existing.status == "failed_retryable" and existing.next_retry_at:
            retry_at = existing.next_retry_at
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            if retry_at > utcnow():
                return existing

        def _finish(status: str, response: dict) -> NotificationDelivery:
            """Terminal/skip outcome: update the retrying row in place instead of
            inserting a duplicate idempotency-key row (which crashes on the
            uq_notification_idempotency constraint)."""
            extras = {
                key: metadata[key]
                for key in ("automation_key", "report_id")
                if metadata.get(key)
            }
            if existing is not None:
                existing.status = status
                existing.provider_response = response
                existing.last_attempt_at = utcnow()
                existing.next_retry_at = None
                existing.last_error = None
                if extras:
                    existing.payload = {**(existing.payload or {}), **extras}
                db.commit()
                db.refresh(existing)
                return existing
            delivery = self._create_delivery(db, user_id, channel, recipient, message, idempotency_key, status, response, locale=locale)
            if extras:
                delivery.payload = {**(delivery.payload or {}), **extras}
                db.commit()
                db.refresh(delivery)
            return delivery

        pref = user.preference
        locale = normalize_locale(
            metadata.get("locale") or getattr(pref, "locale", None)
        )
        recipient = self._recipient(user_id, pref, channel, metadata)
        if channel == "email":
            # Hard bind email deliveries to the verified account email (defense
            # in depth; onboarding already enforces this at write time).
            recipient = user.email
        if channel == "web":
            # Web inbox: the persisted delivery row is the audit trail; the web
            # reports library reads Report rows directly. No external provider,
            # no credits.
            return _finish("sent", {"reason": "web_inbox"})
        if not recipient:
            return _finish("skipped", {"reason": "missing_recipient"})
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
                "push": self.settings.apns_enabled,
            }.get(channel, False)
            if not configured:
                return _finish("failed", {"reason": "provider_not_configured"})
        if channel == "imessage":
            try:
                recipient = normalize_e164(recipient)
            except ValueError:
                return _finish("skipped", {"reason": "invalid_recipient"})
            if self.settings.imessage_provider == "macos_relay" and (not pref.imessage_recipient_verified_at or pref.imessage_recipient != recipient):
                return _finish("skipped", {"reason": "recipient_unverified"})
            if len(message) > self.settings.imessage_max_message_length:
                return _finish("skipped", {"reason": "message_too_long"})
            if self._imessage_count_today(db, user_id) >= self.settings.imessage_rate_limit_per_user_per_day:
                return _finish("skipped", {"reason": "daily_rate_limit"})
        if channel not in CHANNEL_ACTION:
            return _finish("failed", {"reason": "unsupported_channel"})
        action = CHANNEL_ACTION[channel]
        attempt = (existing.attempt_count if existing else 0) + 1
        quote = quote_task(task_type=action, notification_channel=channel)
        reservation = None
        try:
            assert_action_allowed(db, user_id, action)
            reservation = reserve_task(
                db,
                user_id,
                quote,
                f"notification-charge:{idempotency_key}:{attempt}",
                {"channel": channel, "idempotency_key": idempotency_key, **({"automation_key": metadata["automation_key"]} if metadata.get("automation_key") else {})},
            )
            db.commit()
        except (InsufficientCreditsError, EntitlementDeniedError, AutomationBudgetExceeded) as exc:
            db.rollback()
            if isinstance(exc, AutomationBudgetExceeded) and metadata.get("automation_key"):
                from packages.billing.budgets import pause_automation_budget

                pause_automation_budget(
                    db,
                    user_id,
                    str(metadata["automation_key"]),
                    str(exc),
                )
                db.commit()
            skip_status = (
                "skipped_insufficient_credits"
                if isinstance(exc, InsufficientCreditsError)
                else "skipped_budget"
                if isinstance(exc, AutomationBudgetExceeded)
                else "skipped_entitlement"
            )
            return _finish(
                skip_status,
                {
                    "reason": "insufficient_credits"
                    if isinstance(exc, InsufficientCreditsError)
                    else "automation_budget_exceeded"
                    if isinstance(exc, AutomationBudgetExceeded)
                    else "entitlement_denied"
                },
            )
        if channel == "push":
            devices = db.query(PushDevice).filter_by(user_id=user_id, enabled=True).all()
            provider = APNsProvider(db, devices)
        else:
            provider = self._provider(channel)
        try:
            result = provider.send(recipient, message, idempotency_key)
        except Exception:
            if reservation:
                refund_task(db, user_id, reservation, "NOTIFICATION_PROVIDER_EXCEPTION", metadata={"channel": channel})
                db.commit()
            raise
        permanent = result.response.get("status") in {"unsupported_os", "invalid_recipient", "message_too_long", "missing_applescript"}
        status = "sent" if result.ok else ("failed_permanent" if permanent else "failed_retryable") if channel in {"imessage", "push"} else "failed"
        if not result.ok:
            refund_task(
                db, user_id, reservation, "NOTIFICATION_PROVIDER_FAILURE",
                metadata={"channel": channel, "idempotency_key": idempotency_key},
            )
            db.commit()
        else:
            settle_task(
                db,
                user_id,
                reservation,
                quote.credits,
                metadata={"channel": channel, "idempotency_key": idempotency_key},
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
        delivery.payload = {
            "message": message,
            **({"automation_key": metadata["automation_key"]} if metadata.get("automation_key") else {}),
            **({"report_id": metadata["report_id"]} if metadata.get("report_id") else {}),
        }
        delivery.attempt_count = attempt
        delivery.last_attempt_at = utcnow()
        delivery.next_retry_at = next_retry_at
        delivery.last_error = None if result.ok else "provider_failed"
        db.commit()
        db.refresh(delivery)
        return delivery
