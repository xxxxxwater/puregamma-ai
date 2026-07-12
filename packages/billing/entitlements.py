from __future__ import annotations

from packages.billing.credits import HIGH_COST_ACTIONS
from packages.billing.plans import get_plan


def entitlement_for_plan(plan_name: str, subscription_status: str | None = None) -> dict:
    plan = get_plan(plan_name)
    restricted = subscription_status in {"past_due", "unpaid", "incomplete_expired", "deleted", "canceled"}
    return {
        "plan": plan.name,
        "monthly_credits": plan.monthly_credits,
        "agent_daily_runs": plan.agent_daily_runs,
        "agent_concurrent_runs": plan.agent_concurrent_runs,
        "max_portfolios": plan.max_portfolios,
        "max_daily_reports": plan.max_daily_reports,
        "max_alerts": plan.max_alerts_per_month,
        "max_alerts_per_month": plan.max_alerts_per_month,
        "allowed_data_sources": list(plan.allowed_data_sources),
        "notification_channels": list(plan.notification_channels),
        "backtest_tier": plan.backtest_tier,
        "monitoring_tier": plan.monitoring_tier,
        "queue_priority": plan.queue_priority,
        "private_playbooks": plan.private_playbooks and not restricted,
        "high_cost_tasks": plan.high_cost_enabled and not restricted,
        "imessage": plan.imessage_enabled and not restricted,
        "imessage_enabled": plan.imessage_enabled and not restricted,
        "restricted_reason": ("payment_failed" if subscription_status == "past_due" else "subscription_restricted") if restricted else None,
    }


def can_run_action(plan_name: str, action: str, subscription_status: str | None = None) -> bool:
    entitlement = entitlement_for_plan(plan_name, subscription_status)
    if subscription_status in {"past_due", "unpaid", "incomplete_expired", "deleted", "canceled"}:
        return action not in HIGH_COST_ACTIONS and action == "email_alert"
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
