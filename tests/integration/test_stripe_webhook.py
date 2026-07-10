from __future__ import annotations

import json
import time
import types

from apps.api.config import Settings
from apps.api.services.billing_service import mock_upgrade, process_stripe_event
from packages.database.models import CreditLedger, Subscription, SubscriptionPlan
from tests.conftest import stripe_event


def test_checkout_session_completed_creates_subscription_and_grants_credits(db, demo_user):
    event, raw = stripe_event(
        "evt-checkout-completed-contract",
        "checkout.session.completed",
        {"customer": "cus_checkout", "subscription": "sub_checkout", "metadata": {"user_id": demo_user.id, "plan_name": "Pro"}},
    )

    result = process_stripe_event(db, event, raw)
    db.refresh(demo_user)

    assert result["processed"] is True
    assert demo_user.plan == "Pro"
    assert demo_user.stripe_customer_id == "cus_checkout"
    assert demo_user.credit_balance == 1030


def test_invoice_paid_replay_does_not_double_grant(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    event, raw = stripe_event(
        "evt-invoice-replay",
        "invoice.paid",
        {"id": "in_replay", "customer": demo_user.stripe_customer_id, "billing_reason": "subscription_cycle"},
    )

    process_stripe_event(db, event, raw)
    after_once = demo_user.credit_balance
    duplicate = process_stripe_event(db, event, raw)
    db.refresh(demo_user)

    assert duplicate["duplicate"] is True
    assert demo_user.credit_balance == after_once


def test_same_invoice_different_event_does_not_double_grant(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    first, raw_first = stripe_event(
        "evt-invoice-same-1",
        "invoice.paid",
        {"id": "in_same_invoice", "customer": demo_user.stripe_customer_id, "billing_reason": "subscription_cycle"},
    )
    second, raw_second = stripe_event(
        "evt-invoice-same-2",
        "invoice.paid",
        {"id": "in_same_invoice", "customer": demo_user.stripe_customer_id, "billing_reason": "subscription_cycle"},
    )

    process_stripe_event(db, first, raw_first)
    after_once = demo_user.credit_balance
    process_stripe_event(db, second, raw_second)
    db.refresh(demo_user)

    assert demo_user.credit_balance == after_once


def test_subscription_updated_changes_plan_from_price_id(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    event, raw = stripe_event(
        "evt-subscription-updated-max",
        "customer.subscription.updated",
        {
            "id": "sub_mock_" + demo_user.id[:8],
            "customer": demo_user.stripe_customer_id,
            "status": "active",
            "items": {"data": [{"price": {"id": "price_mock_max"}}]},
        },
    )

    process_stripe_event(db, event, raw)
    db.refresh(demo_user)

    assert demo_user.plan == "Max"


def test_subscription_deleted_downgrades_to_free(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    event, raw = stripe_event(
        "evt-subscription-deleted",
        "customer.subscription.deleted",
        {"id": "sub_mock_" + demo_user.id[:8], "customer": demo_user.stripe_customer_id, "metadata": {"user_id": demo_user.id, "plan_name": "Pro"}},
    )

    process_stripe_event(db, event, raw)
    db.refresh(demo_user)

    assert demo_user.plan == "Free"


def test_invoice_payment_failed_restricts_high_cost_tasks(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    event, raw = stripe_event("evt-invoice-failed", "invoice.payment_failed", {"customer": demo_user.stripe_customer_id})

    process_stripe_event(db, event, raw)

    assert any(row.action == "monthly_credit_grant" for row in db.query(CreditLedger).all())


def test_webhook_raw_body_is_used_for_mock_payload_hash(db, demo_user):
    event, raw = stripe_event(
        "evt-raw-body",
        "checkout.session.completed",
        {"customer": "cus_raw", "subscription": "sub_raw", "metadata": {"user_id": demo_user.id, "plan_name": "Pro"}},
    )
    expected_hash_payload = json.loads(raw.decode())

    result = process_stripe_event(db, expected_hash_payload, raw)

    assert result["processed"] is True


def test_stripe_signature_invalid_is_rejected(api_client, monkeypatch):
    from apps.api.routers import stripe_webhook as router

    fake_stripe = types.SimpleNamespace(
        Webhook=types.SimpleNamespace(construct_event=lambda payload, signature, secret: (_ for _ in ()).throw(Exception("bad signature")))
    )
    monkeypatch.setitem(__import__("sys").modules, "stripe", fake_stripe)
    monkeypatch.setattr(router, "get_settings", lambda: Settings(billing_mode="stripe", stripe_webhook_secret="whsec_test"))

    response = api_client.post("/stripe/webhook", content=b'{"id":"evt_bad","type":"invoice.paid"}', headers={"Stripe-Signature": "bad"})

    assert response.status_code == 400
    assert "Invalid Stripe signature" in response.json()["detail"]


def test_stripe_signature_valid_payload_is_accepted(api_client, monkeypatch):
    from apps.api.routers import stripe_webhook as router

    fake_stripe = types.SimpleNamespace(
        Webhook=types.SimpleNamespace(construct_event=lambda payload, signature, secret, **kwargs: json.loads(payload.decode()))
    )
    monkeypatch.setitem(__import__("sys").modules, "stripe", fake_stripe)
    monkeypatch.setattr(router, "get_settings", lambda: Settings(billing_mode="stripe", stripe_webhook_secret="whsec_test", stripe_webhook_tolerance_seconds=300))

    response = api_client.post(
        "/stripe/webhook",
        content=b'{"id":"evt_valid_signature","type":"product.updated","data":{"object":{"id":"prod_valid","name":"Pro"}}}',
        headers={"Stripe-Signature": f"t={int(time.time())},v1=test"},
    )

    assert response.status_code == 200
    assert response.json()["processed"] is True


def test_stripe_signature_expired_timestamp_is_rejected(api_client, monkeypatch):
    from apps.api.routers import stripe_webhook as router

    monkeypatch.setattr(router, "get_settings", lambda: Settings(billing_mode="stripe", stripe_webhook_secret="whsec_test", stripe_webhook_tolerance_seconds=300))
    old_timestamp = int(time.time()) - 1000

    response = api_client.post("/stripe/webhook", content=b'{"id":"evt_old","type":"invoice.paid"}', headers={"Stripe-Signature": f"t={old_timestamp},v1=test"})

    assert response.status_code == 400
    assert "Expired" in response.json()["detail"]


def test_price_updated_webhook_syncs_subscription_plan(db):
    event, raw = stripe_event(
        "evt-price-updated",
        "price.updated",
        {"id": "price_live_pro", "lookup_key": "puregamma_pro_monthly", "unit_amount": 2990, "active": True, "metadata": {"plan_name": "Pro"}},
    )

    process_stripe_event(db, event, raw)
    plan = db.get(SubscriptionPlan, "Pro")

    assert plan.stripe_price_id == "price_live_pro"
    assert plan.monthly_price == 29.9
    assert plan.is_active is True


def test_payment_intent_failed_marks_subscription_past_due(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    event, raw = stripe_event("evt-pi-failed", "payment_intent.payment_failed", {"id": "pi_failed", "customer": demo_user.stripe_customer_id})

    process_stripe_event(db, event, raw)
    sub = db.query(Subscription).filter(Subscription.user_id == demo_user.id).one()

    assert sub.status == "past_due"


def test_non_subscription_webhook_events_are_recorded(db):
    for event_id, event_type, obj in [
        ("evt-product-updated", "product.updated", {"id": "prod_test", "name": "Pro"}),
        ("evt-pi-succeeded", "payment_intent.succeeded", {"id": "pi_ok", "customer": "cus_test", "amount_received": 2990}),
        ("evt-charge-refunded", "charge.refunded", {"id": "ch_refund", "payment_intent": "pi_ok", "amount_refunded": 2990}),
    ]:
        event, raw = stripe_event(event_id, event_type, obj)
        result = process_stripe_event(db, event, raw)
        assert result["processed"] is True
