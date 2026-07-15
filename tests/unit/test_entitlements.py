from __future__ import annotations

from apps.api.services.billing_service import mock_upgrade, process_stripe_event
from apps.api.services.entitlement_service import EntitlementDeniedError, assert_action_allowed, get_user_entitlement
from packages.billing.entitlements import can_run_action, entitlement_for_plan
from tests.conftest import stripe_event


def test_free_entitlement_defaults_to_low_cost_email_only(demo_user, db):
    entitlement = get_user_entitlement(db, demo_user.id)

    assert entitlement["plan"] == "Free"
    assert entitlement["monthly_credits"] == 150
    assert entitlement["notification_channels"] == ["email", "push"]
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
    assert entitlement["subscribed_plan"] == "Max"
    assert entitlement["effective_plan"] == "Free"
    assert entitlement["plan"] == "Free"
    assert entitlement["agent_daily_runs"] == entitlement_for_plan("Free")["agent_daily_runs"]
    assert entitlement["agent_concurrent_runs"] == entitlement_for_plan("Free")["agent_concurrent_runs"]
    assert entitlement["allowed_data_sources"] == entitlement_for_plan("Free")["allowed_data_sources"]
    assert entitlement["queue_priority"] == 0
    assert entitlement["backtest_tier"] == "none"
    assert entitlement["monitoring_tier"] == "basic"
    assert entitlement["max_portfolios"] == 0
    assert entitlement["portfolio_access"] == "read_only"
    assert entitlement["notification_channels"] == ["email", "push"]
    assert can_run_action("Max", "daily_market_report", "past_due") is False


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
    assert entitlement["monthly_credits"] == 150
    assert can_run_action("ForgedMax", "imessage_alert") is False


def test_plan_credit_and_carryover_policy_matches_commercial_baseline():
    free = entitlement_for_plan("Free")
    invite = entitlement_for_plan("Invite Preview")
    pro = entitlement_for_plan("Pro")
    max_plan = entitlement_for_plan("Max")

    assert (free["monthly_credits"], free["daily_bonus"], free["monthly_bonus_cap"]) == (150, 10, 300)
    assert (invite["monthly_credits"], invite["daily_bonus"], invite["welcome_grant"]) == (300, 20, 1000)
    assert pro["carryover_cap"] == 6000
    assert max_plan["carryover_cap"] == 30000


def test_terminated_subscription_uses_complete_free_baseline():
    baseline = entitlement_for_plan("Free")
    for status in ("unpaid", "incomplete_expired", "canceled", "deleted"):
        entitlement = entitlement_for_plan("Max", status)
        assert entitlement["subscribed_plan"] == "Max"
        assert entitlement["effective_plan"] == "Free"
        for field in ("agent_daily_runs", "agent_concurrent_runs", "max_portfolios", "max_daily_reports", "max_alerts_per_month", "allowed_data_sources", "notification_channels", "backtest_tier", "monitoring_tier", "queue_priority"):
            assert entitlement[field] == baseline[field]
