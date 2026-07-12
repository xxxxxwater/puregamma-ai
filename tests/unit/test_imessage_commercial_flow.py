from datetime import timedelta

from apps.api.services.billing_service import mock_upgrade
from apps.api.services.notification_service import send_notification
from packages.database.models import NotificationDelivery, utcnow
from packages.notifications.base import NotificationResult
from packages.notifications.dispatcher import NotificationDispatcher
from tests.conftest import auth_headers


def test_imessage_verification_request_and_confirm(api_client, db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    requested = api_client.post("/notifications/imessage/verify/request", json={"recipient": "+1 (555) 555-0100"}, headers=auth_headers(demo_user))

    assert requested.status_code == 200
    payload = requested.json()
    assert payload["recipient"] == "+15555550100"
    assert payload["development_code"]

    confirmed = api_client.post("/notifications/imessage/verify/confirm", json={"challenge_id": payload["challenge_id"], "code": payload["development_code"]}, headers=auth_headers(demo_user))

    assert confirmed.status_code == 200
    db.refresh(demo_user.preference)
    assert demo_user.preference.imessage_recipient_verified_at is not None


def test_retryable_notification_can_retry_same_idempotency_key(monkeypatch, db, max_user):
    outcomes = iter([NotificationResult(False, "imessage", {"status": "timeout"}), NotificationResult(True, "imessage", {"status": "sent"})])
    monkeypatch.setattr(NotificationDispatcher, "_provider", lambda self, channel: type("Provider", (), {"send": lambda self, recipient, message, key: next(outcomes)})())
    before = max_user.credit_balance

    first = send_notification(db, max_user.id, "imessage", "retry me", {"idempotency_key": "retry-imessage"})
    assert first.status == "failed_retryable"
    first.next_retry_at = utcnow() - timedelta(seconds=1)
    db.commit()
    second = send_notification(db, max_user.id, "imessage", "retry me", {"idempotency_key": "retry-imessage"})

    db.refresh(max_user)
    assert second.id == first.id
    assert second.status == "sent"
    assert second.attempt_count == 2
    assert max_user.credit_balance == before - 3
    assert db.query(NotificationDelivery).filter_by(idempotency_key="retry-imessage").count() == 1
