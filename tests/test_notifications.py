from __future__ import annotations

from apps.api.services.billing_service import mock_upgrade
from apps.api.services.notification_service import send_notification
from packages.notifications.base import NotificationResult
from packages.notifications.dispatcher import NotificationDispatcher
from packages.notifications.imessage.webhook_gateway import compute_hmac, verify_hmac_signature


def test_telegram_mock_send(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    delivery = send_notification(db, demo_user.id, "telegram", "telegram test. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"idempotency_key": "tg-1"})
    assert delivery.status == "sent"
    assert delivery.provider_response["mode"] == "mock"


def test_slack_mock_send(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    delivery = send_notification(db, demo_user.id, "slack", "slack test. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"idempotency_key": "slack-1"})
    assert delivery.status == "sent"


def test_email_mock_send(db, demo_user):
    delivery = send_notification(db, demo_user.id, "email", "email test. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"idempotency_key": "email-1"})
    assert delivery.status == "sent"


def test_imessage_mock_send(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    delivery = send_notification(db, demo_user.id, "imessage", "iMessage test. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"idempotency_key": "imsg-1"})
    assert delivery.status == "sent"
    assert delivery.provider_response["mode"] == "mock"


def test_imessage_entitlement_denied_for_free(db, demo_user):
    delivery = send_notification(db, demo_user.id, "imessage", "blocked. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"idempotency_key": "imsg-free"})
    assert delivery.status == "skipped_entitlement"
    assert delivery.provider_response["reason"] == "entitlement_denied"


def test_imessage_credit_consumption(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    before = demo_user.credit_balance
    delivery = send_notification(db, demo_user.id, "imessage", "credit test. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"idempotency_key": "imsg-credit"})
    db.refresh(demo_user)
    assert delivery.status == "sent"
    assert demo_user.credit_balance == before - 2


def test_imessage_idempotency(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    before = demo_user.credit_balance
    first = send_notification(db, demo_user.id, "imessage", "same message. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"idempotency_key": "imsg-dupe"})
    second = send_notification(db, demo_user.id, "imessage", "same message. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"idempotency_key": "imsg-dupe"})
    db.refresh(demo_user)
    assert first.id == second.id
    assert demo_user.credit_balance == before - 2


def test_failed_notification_refunds_credits(monkeypatch, db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    before = demo_user.credit_balance

    class FailingProvider:
        def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
            return NotificationResult(False, "telegram", {"error": "provider_down"})

    monkeypatch.setattr(NotificationDispatcher, "_provider", lambda self, channel: FailingProvider())
    delivery = send_notification(db, demo_user.id, "telegram", "refund test. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"idempotency_key": "tg-refund"})
    db.refresh(demo_user)
    assert delivery.status == "failed"
    assert demo_user.credit_balance == before


def test_imessage_relay_hmac_verification(hmac_payload):
    body, timestamp = hmac_payload
    signature = compute_hmac("secret", timestamp, body)
    assert verify_hmac_signature("secret", timestamp, body, signature)
    assert not verify_hmac_signature("secret", timestamp, body, "bad")
