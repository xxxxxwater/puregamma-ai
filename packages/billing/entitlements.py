from __future__ import annotations

from packages.billing.credits import HIGH_COST_ACTIONS
from packages.billing.plans import get_plan


TERMINATED_STATUSES = {"unpaid", "incomplete_expired", "deleted", "canceled", "inactive"}
RESTRICTED_STATUSES = {"past_due", *TERMINATED_STATUSES}


def entitlement_for_plan(plan_name: str, subscription_status: str | None = None) -> dict:
    subscribed = get_plan(plan_name)
    restricted = subscription_status in RESTRICTED_STATUSES
    effective = get_plan("Free") if restricted else subscribed
    restricted_reason = None
    if subscription_status == "past_due":
        restricted_reason = "payment_failed"
    elif restricted:
        restricted_reason = "subscription_restricted"
    return {
        "plan": effective.name,
        "subscribed_plan": subscribed.name,
        "effective_plan": effective.name,
        "subscription_status": subscription_status,
        "monthly_credits": effective.monthly_credits,
        "daily_bonus": effective.daily_bonus,
        "monthly_bonus_cap": effective.monthly_bonus_cap,
        "carryover_cap": effective.carryover_cap,
        "welcome_grant": effective.welcome_grant,
        "agent_daily_runs": effective.agent_daily_runs,
        "agent_concurrent_runs": effective.agent_concurrent_runs,
        "max_portfolios": effective.max_portfolios,
        "portfolio_access": "read_only" if restricted else "standard",
        "max_daily_reports": effective.max_daily_reports,
        "max_alerts": effective.max_alerts_per_month,
        "max_alerts_per_month": effective.max_alerts_per_month,
        "allowed_data_sources": list(effective.allowed_data_sources),
        "notification_channels": list(effective.notification_channels),
        "backtest_tier": effective.backtest_tier,
        "monitoring_tier": effective.monitoring_tier,
        "queue_priority": effective.queue_priority,
        "private_playbooks": effective.private_playbooks,
        "high_cost_tasks": effective.high_cost_enabled,
        "imessage": effective.imessage_enabled,
        "imessage_enabled": effective.imessage_enabled,
        "restricted_reason": restricted_reason,
    }


def can_run_action(plan_name: str, action: str, subscription_status: str | None = None) -> bool:
    entitlement = entitlement_for_plan(plan_name, subscription_status)
    if subscription_status == "past_due" and action == "daily_market_report":
        return False
    channel_actions = {
        "email_alert": "email",
        "telegram_alert": "telegram",
        "slack_alert": "slack",
        "imessage_alert": "imessage",
    }
    channel = channel_actions.get(action)
    if channel:
        return channel in entitlement["notification_channels"]
    if action in HIGH_COST_ACTIONS:
        return bool(entitlement["high_cost_tasks"])
    return True
