from __future__ import annotations

from apps.api.services.billing_service import mock_upgrade
from apps.api.services.notification_service import send_notification
from packages.notifications.base import NotificationResult
from packages.notifications.dispatcher import NotificationDispatcher
from packages.notifications.imessage.webhook_gateway import compute_hmac, verify_hmac_signature


def test_telegram_mock_send_is_never_reported_as_delivered(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    before = demo_user.credit_balance
    delivery = send_notification(db, demo_user.id, "telegram", "telegram test", {"idempotency_key": "tg-1"})
    db.refresh(demo_user)
    assert delivery.status == "skipped"
    assert delivery.provider_response["reason"] == "mock_recipient"
    assert demo_user.credit_balance == before


def test_slack_mock_send_is_never_reported_as_delivered(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    before = demo_user.credit_balance
    delivery = send_notification(db, demo_user.id, "slack", "slack test", {"idempotency_key": "slack-1"})
    db.refresh(demo_user)
    assert delivery.status == "skipped"
    assert delivery.provider_response["reason"] == "mock_recipient"
    assert demo_user.credit_balance == before


def test_email_mock_send_is_never_reported_as_delivered(db, demo_user):
    before = demo_user.credit_balance
    delivery = send_notification(db, demo_user.id, "email", "email test", {"idempotency_key": "email-1"})
    db.refresh(demo_user)
    assert delivery.status == "skipped"
    assert delivery.provider_response["reason"] == "mock_recipient"
    assert demo_user.credit_balance == before


def test_imessage_mock_send_is_never_reported_as_delivered(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    before = demo_user.credit_balance
    delivery = send_notification(db, demo_user.id, "imessage", "iMessage test", {"idempotency_key": "imsg-1"})
    db.refresh(demo_user)
    assert delivery.status == "skipped"
    assert delivery.provider_response["reason"] == "mock_recipient"
    assert demo_user.credit_balance == before


def test_imessage_entitlement_denied_for_free(db, demo_user):
    delivery = send_notification(db, demo_user.id, "imessage", "blocked", {"idempotency_key": "imsg-free"})
    assert delivery.status == "skipped_entitlement"
    assert delivery.provider_response["reason"] == "entitlement_denied"


def test_imessage_mock_does_not_consume_credits(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    before = demo_user.credit_balance
    delivery = send_notification(db, demo_user.id, "imessage", "credit test", {"idempotency_key": "imsg-credit"})
    db.refresh(demo_user)
    assert delivery.status == "skipped"
    assert demo_user.credit_balance == before


def test_imessage_idempotency(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    before = demo_user.credit_balance
    first = send_notification(db, demo_user.id, "imessage", "same message", {"idempotency_key": "imsg-dupe"})
    second = send_notification(db, demo_user.id, "imessage", "same message", {"idempotency_key": "imsg-dupe"})
    db.refresh(demo_user)
    assert first.id == second.id
    assert first.status == "skipped"
    assert demo_user.credit_balance == before


def test_failed_notification_refunds_credits(monkeypatch, db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    before = demo_user.credit_balance

    class FailingProvider:
        def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
            return NotificationResult(False, "telegram", {"error": "provider_down"})

    monkeypatch.setattr(NotificationDispatcher, "_provider", lambda self, channel: FailingProvider())
    delivery = send_notification(db, demo_user.id, "telegram", "refund test", {"idempotency_key": "tg-refund"})
    db.refresh(demo_user)
    assert delivery.status == "failed"
    assert demo_user.credit_balance == before


def test_provider_exception_is_persisted_and_refunded(monkeypatch, db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    before = demo_user.credit_balance

    class RaisingProvider:
        def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
            raise RuntimeError("upstream secret detail must not escape")

    monkeypatch.setattr(NotificationDispatcher, "_provider", lambda self, channel: RaisingProvider())
    delivery = send_notification(db, demo_user.id, "telegram", "exception test", {"idempotency_key": "tg-exception"})
    db.refresh(demo_user)

    assert delivery.status == "failed"
    assert delivery.provider_response == {
        "error": "provider_exception",
        "exception_type": "RuntimeError",
    }
    assert demo_user.credit_balance == before


def test_imessage_relay_hmac_verification(hmac_payload):
    body, timestamp = hmac_payload
    signature = compute_hmac("secret", timestamp, body)
    assert verify_hmac_signature("secret", timestamp, body, signature)
    assert not verify_hmac_signature("secret", timestamp, body, "bad")
