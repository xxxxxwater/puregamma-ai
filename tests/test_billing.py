from __future__ import annotations

import pytest

from apps.api.services.billing_service import create_checkout_session, create_payment_link_checkout, get_subscription, mock_upgrade, process_stripe_event, resolve_checkout_intent
from apps.api.services.credit_service import InsufficientCreditsError, consume_credits, grant_credits
from apps.api.services.entitlement_service import get_user_entitlement
from packages.database.models import BillingCheckoutIntent, CreditLedger, StripeWebhookEvent
from tests.conftest import stripe_event


def test_credit_consume(db, demo_user):
    consume_credits(db, demo_user.id, "daily_market_report", 10)
    db.commit()
    assert demo_user.credit_balance == 140


def test_insufficient_credits(db, demo_user):
    with pytest.raises(InsufficientCreditsError):
        consume_credits(db, demo_user.id, "backtest", 1000)


def test_monthly_credit_grant(db, demo_user):
    grant_credits(db, demo_user.id, "monthly_credit_grant", 1000)
    db.commit()
    assert demo_user.credit_balance == 1150


def test_mock_upgrade(db, demo_user):
    result = mock_upgrade(db, demo_user.id, "Pro")
    assert result["plan"] == "Pro"
    assert result["credit_balance"] == 3150


def test_stripe_checkout_session_creation_mock(db, demo_user):
    result = create_checkout_session(db, demo_user.id, "Pro")
    assert result["mode"] == "mock"
    assert "checkout_url" in result


def test_stripe_payment_link_checkout_creates_intent_without_user_pii(db, demo_user):
    result = create_payment_link_checkout(db, demo_user.id, "Pro")
    intent = db.query(BillingCheckoutIntent).filter(BillingCheckoutIntent.public_reference == result["client_reference_id"]).one()

    assert result["checkout_mode"] == "payment_link"
    assert "client_reference_id=" in result["checkout_url"]
    assert demo_user.email not in result["checkout_url"]
    assert intent.checkout_mode == "payment_link"
    assert intent.status == "created"
    assert intent.metadata_json["payment_link_plan_mapping"] == "unknown"


def test_primary_payment_link_checkout_requires_manual_review(db, demo_user):
    result = create_payment_link_checkout(db, demo_user.id, "Pro")
    event, raw = stripe_event(
        "evt_primary_payment_link",
        "checkout.session.completed",
        {
            "id": "cs_primary_link",
            "customer": "cus_primary",
            "subscription": "sub_primary",
            "payment_status": "paid",
            "client_reference_id": result["client_reference_id"],
        },
    )

    processed = process_stripe_event(db, event, raw)
    intent = db.query(BillingCheckoutIntent).filter(BillingCheckoutIntent.public_reference == result["client_reference_id"]).one()
    webhook = db.query(StripeWebhookEvent).filter(StripeWebhookEvent.stripe_event_id == "evt_primary_payment_link").one()
    db.refresh(demo_user)

    assert processed["requires_manual_review"] is True
    assert intent.status == "requires_manual_review"
    assert webhook.requires_manual_review is True
    assert demo_user.plan == "Free"


def test_admin_resolve_checkout_intent_grants_credits_once(db, demo_user):
    result = create_payment_link_checkout(db, demo_user.id, "Pro")
    event, raw = stripe_event(
        "evt_primary_payment_link_resolve",
        "checkout.session.completed",
        {
            "id": "cs_primary_resolve",
            "customer": "cus_primary_resolve",
            "subscription": "sub_primary_resolve",
            "payment_status": "paid",
            "client_reference_id": result["client_reference_id"],
        },
    )
    process_stripe_event(db, event, raw)
    intent = db.query(BillingCheckoutIntent).filter(BillingCheckoutIntent.public_reference == result["client_reference_id"]).one()

    resolve_checkout_intent(db, intent.id, demo_user.id, "Pro", "admin-test")
    db.refresh(demo_user)
    after_once = demo_user.credit_balance
    resolve_checkout_intent(db, intent.id, demo_user.id, "Pro", "admin-test")
    db.refresh(demo_user)
    grants = (
        db.query(CreditLedger)
        .filter(CreditLedger.action == "monthly_credit_grant", CreditLedger.metadata_json["manual_resolve_intent_id"].as_string() == intent.id)
        .all()
    )

    assert demo_user.plan == "Pro"
    assert after_once == 3150
    assert demo_user.credit_balance == after_once
    assert len(grants) == 1


def test_stripe_webhook_checkout_completed(db, demo_user):
    event, raw = stripe_event(
        "evt_checkout",
        "checkout.session.completed",
        {"customer": "cus_test", "subscription": "sub_test", "metadata": {"user_id": demo_user.id, "plan_name": "Pro"}},
    )
    result = process_stripe_event(db, event, raw)
    db.refresh(demo_user)
    assert result["processed"] is True
    assert demo_user.plan == "Pro"
    assert demo_user.credit_balance == 3150
    assert demo_user.stripe_customer_id == "cus_test"


def test_stripe_webhook_invoice_paid(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    db.refresh(demo_user)
    before = demo_user.credit_balance
    event, raw = stripe_event(
        "evt_invoice",
        "invoice.paid",
        {"id": "in_test", "customer": demo_user.stripe_customer_id, "billing_reason": "subscription_cycle"},
    )
    process_stripe_event(db, event, raw)
    db.refresh(demo_user)
    assert demo_user.credit_balance == min(before + 3000, 6000)


def test_stripe_webhook_duplicated_event_should_not_double_grant_credits(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    db.refresh(demo_user)
    event, raw = stripe_event(
        "evt_invoice_dupe",
        "invoice.paid",
        {"id": "in_dupe", "customer": demo_user.stripe_customer_id, "billing_reason": "subscription_cycle"},
    )
    process_stripe_event(db, event, raw)
    after_once = demo_user.credit_balance
    result = process_stripe_event(db, event, raw)
    db.refresh(demo_user)
    assert result["duplicate"] is True
    assert demo_user.credit_balance == after_once


def test_stripe_webhook_same_invoice_different_event_should_not_double_grant_credits(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    db.refresh(demo_user)
    first, raw_first = stripe_event(
        "evt_invoice_first",
        "invoice.paid",
        {"id": "in_same", "customer": demo_user.stripe_customer_id, "billing_reason": "subscription_cycle"},
    )
    second, raw_second = stripe_event(
        "evt_invoice_second",
        "invoice.paid",
        {"id": "in_same", "customer": demo_user.stripe_customer_id, "billing_reason": "subscription_cycle"},
    )
    process_stripe_event(db, first, raw_first)
    after_once = demo_user.credit_balance
    process_stripe_event(db, second, raw_second)
    db.refresh(demo_user)
    assert demo_user.credit_balance == after_once


def test_subscription_cancellation_downgrade(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    event, raw = stripe_event(
        "evt_deleted",
        "customer.subscription.deleted",
        {"id": "sub_mock_" + demo_user.id[:8], "customer": demo_user.stripe_customer_id, "metadata": {"user_id": demo_user.id, "plan_name": "Pro"}},
    )
    process_stripe_event(db, event, raw)
    db.refresh(demo_user)
    assert demo_user.plan == "Free"
    assert get_subscription(db, demo_user.id)["subscription_status"] == "deleted"


def test_payment_failed_entitlement_restriction(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    event, raw = stripe_event("evt_failed", "invoice.payment_failed", {"customer": demo_user.stripe_customer_id})
    process_stripe_event(db, event, raw)
    entitlement = get_user_entitlement(db, demo_user.id)
    assert entitlement["high_cost_tasks"] is False
    assert entitlement["restricted_reason"] == "payment_failed"
