from __future__ import annotations

from apps.api.services.billing_service import mock_upgrade, process_stripe_event
from apps.api.services.entitlement_service import EntitlementDeniedError, assert_action_allowed, get_user_entitlement
from packages.billing.entitlements import can_run_action, entitlement_for_plan
from tests.conftest import stripe_event


def test_free_entitlement_defaults_to_low_cost_email_only(demo_user, db):
    entitlement = get_user_entitlement(db, demo_user.id)

    assert entitlement["plan"] == "Free"
    assert entitlement["monthly_credits"] == 30
    assert entitlement["notification_channels"] == ["email"]
    assert entitlement["imessage"] is False
    assert entitlement["high_cost_tasks"] is False


def test_pro_does_not_include_imessage_by_default():
    entitlement = entitlement_for_plan("Pro")

    assert "telegram" in entitlement["notification_channels"]
    assert "email" in entitlement["notification_channels"]
    assert "imessage" not in entitlement["notification_channels"]
    assert entitlement["imessage"] is False


def test_max_includes_imessage_and_high_cost_tasks():
    entitlement = entitlement_for_plan("Max")

    assert entitlement["imessage"] is True
    assert entitlement["high_cost_tasks"] is True
    assert "x" in entitlement["allowed_data_sources"]


def test_payment_failed_restricts_high_cost_and_imessage(db, demo_user):
    mock_upgrade(db, demo_user.id, "Max")
    event, raw = stripe_event("evt-payment-failed-entitlements", "invoice.payment_failed", {"customer": demo_user.stripe_customer_id})
    process_stripe_event(db, event, raw)

    entitlement = get_user_entitlement(db, demo_user.id)

    assert entitlement["high_cost_tasks"] is False
    assert entitlement["imessage"] is False
    assert entitlement["restricted_reason"] == "payment_failed"


def test_past_due_backtest_is_blocked(db, demo_user):
    mock_upgrade(db, demo_user.id, "Pro")
    event, raw = stripe_event("evt-payment-failed-backtest", "invoice.payment_failed", {"customer": demo_user.stripe_customer_id})
    process_stripe_event(db, event, raw)

    try:
        assert_action_allowed(db, demo_user.id, "backtest")
    except EntitlementDeniedError:
        return
    raise AssertionError("past_due subscription should block high-cost backtests")


def test_unknown_plan_falls_back_to_free_entitlements():
    entitlement = entitlement_for_plan("ForgedMax")

    assert entitlement["plan"] == "Free"
    assert entitlement["monthly_credits"] == 30
    assert can_run_action("ForgedMax", "imessage_alert") is False
