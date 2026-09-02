from __future__ import annotations

from datetime import timedelta

from apps.api.services.billing_service import mock_upgrade
from apps.api.services.notification_service import send_notification
from apps.api.config import Settings
from packages.database.models import NotificationDelivery, Report, User, utcnow
from packages.notifications.dispatcher import NotificationDispatcher
from tests.conftest import auth_headers


def test_notification_send_api_email(api_client, demo_user: User):
    response = api_client.post(
        "/notifications/send",
        json={"channel": "email", "message": "API email test", "metadata": {"idempotency_key": "api-email-1"}},
        headers=auth_headers(demo_user),
    )

    assert response.status_code == 200
    # No SMTP credentials in tests: mock provider records a skipped delivery.
    assert response.json()["delivery"]["status"] == "skipped"


def test_report_send_uses_selected_content_and_rejects_stale_report(api_client, db, demo_user: User):
    fresh = Report(
        user_id=demo_user.id,
        title="Fresh report",
        report_type="crypto_daily",
        language="en",
        content_markdown="fresh live market content",
        assets=["BTC"],
        report_date=utcnow().date(),
        status="completed",
        idempotency_key="report-send:fresh",
    )
    stale = Report(
        user_id=demo_user.id,
        title="Stale report",
        report_type="crypto_daily",
        language="en",
        content_markdown="old market content",
        assets=["BTC"],
        report_date=(utcnow() - timedelta(days=2)).date(),
        status="completed",
        idempotency_key="report-send:stale",
        created_at=utcnow() - timedelta(days=2),
    )
    db.add_all([fresh, stale])
    db.commit()

    sent = api_client.post(
        "/notifications/send",
        json={"channel": "email", "report_id": fresh.id},
        headers=auth_headers(demo_user),
    )
    assert sent.status_code == 200
    delivery = db.query(NotificationDelivery).filter_by(idempotency_key=f"manual-report:{fresh.id}:email").one()
    assert delivery.payload["message"] == "fresh live market content"
    assert delivery.payload["report_id"] == fresh.id

    rejected = api_client.post(
        "/notifications/send",
        json={"channel": "email", "report_id": stale.id},
        headers=auth_headers(demo_user),
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "REPORT_STALE"


def test_duplicate_idempotency_key_does_not_double_send_or_charge(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    before = demo_user.credit_balance

    first = send_notification(db, demo_user.id, "imessage", "same body", {"idempotency_key": "dup-imessage"})
    second = send_notification(db, demo_user.id, "imessage", "same body", {"idempotency_key": "dup-imessage"})
    db.refresh(demo_user)

    assert first.id == second.id
    assert db.query(NotificationDelivery).filter(NotificationDelivery.idempotency_key == "dup-imessage").count() == 1
    # Mock deliveries are never billed: no credit change, and the duplicate
    # did not double-charge.
    assert demo_user.credit_balance == before


def test_pro_default_cannot_send_imessage(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")

    delivery = send_notification(db, demo_user.id, "imessage", "blocked", {"idempotency_key": "pro-imessage-blocked"})

    assert delivery.status == "skipped_entitlement"
    assert delivery.provider_response["reason"] == "entitlement_denied"


def test_max_can_send_imessage(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")

    delivery = send_notification(db, demo_user.id, "imessage", "allowed", {"idempotency_key": "max-imessage-ok"})

    # Mock provider delivers nothing: recorded as skipped and never billed.
    assert delivery.status == "skipped"
    assert delivery.provider_response["reason"] == "mock_recipient"


def test_insufficient_credits_skips_notification(db, user_factory):
    user = user_factory("poor-max@puregamma.ai", plan="Max", credit_balance=1)

    delivery = send_notification(db, user.id, "imessage", "too expensive", {"idempotency_key": "poor-imsg"})

    assert delivery.status == "skipped_insufficient_credits"
    assert delivery.provider_response["reason"] == "insufficient_credits"


def test_imessage_message_length_limit(monkeypatch, db, max_user):
    monkeypatch.setattr(
        NotificationDispatcher,
        "__init__",
        lambda self: setattr(self, "settings", Settings(imessage_max_message_length=5)),
    )

    delivery = send_notification(db, max_user.id, "imessage", "too long", {"idempotency_key": "too-long"})

    assert delivery.status == "skipped"
    assert delivery.provider_response["reason"] == "message_too_long"


def test_imessage_daily_rate_limit(monkeypatch, db, max_user):
    monkeypatch.setattr(
        NotificationDispatcher,
        "__init__",
        lambda self: setattr(self, "settings", Settings(imessage_rate_limit_per_user_per_day=1)),
    )
    # Mock deliveries are recorded as skipped (and never billed), so they do
    # not consume the daily quota. Seed one sent row to exercise the
    # production counting path (real relay deliveries are recorded as sent).
    db.add(
        NotificationDelivery(
            user_id=max_user.id,
            channel="imessage",
            recipient="+15555550100",
            payload={"message": "seed"},
            status="sent",
            idempotency_key="limit-seed",
            created_at=utcnow(),
        )
    )
    db.commit()

    delivery = send_notification(db, max_user.id, "imessage", "first", {"idempotency_key": "limit-first"})

    assert delivery.status == "skipped"
    assert delivery.provider_response["reason"] == "daily_rate_limit"


def test_delivery_status_values_are_persisted(db, demo_user):
    delivery = send_notification(db, demo_user.id, "email", "status test", {"idempotency_key": "status-email"})

    assert delivery.status in {"pending", "sent", "failed", "skipped"}


def test_distinct_skip_status_contract(db, user_factory):
    free_user = user_factory("free-skip@puregamma.ai", plan="Free", credit_balance=150)
    poor_max = user_factory("poor-skip@puregamma.ai", plan="Max", credit_balance=1)

    entitlement = send_notification(
        db,
        free_user.id,
        "imessage",
        "not entitled",
        {"idempotency_key": "status-entitlement"},
    )
    insufficient = send_notification(
        db,
        poor_max.id,
        "imessage",
        "not funded",
        {"idempotency_key": "status-insufficient"},
    )

    assert entitlement.status == "skipped_entitlement"
    assert insufficient.status == "skipped_insufficient_credits"
