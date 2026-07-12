from __future__ import annotations

from packages.billing.credits import HIGH_COST_ACTIONS
from packages.billing.plans import get_plan


def entitlement_for_plan(plan_name: str, subscription_status: str | None = None) -> dict:
    plan = get_plan(plan_name)
    past_due = subscription_status == "past_due"
    return {
        "plan": plan.name,
        "monthly_credits": plan.monthly_credits,
        "max_daily_reports": plan.max_daily_reports,
        "max_alerts": plan.max_alerts,
        "allowed_data_sources": list(plan.allowed_data_sources),
        "notification_channels": list(plan.channels),
        "high_cost_tasks": plan.high_cost_enabled and not past_due,
        "imessage": "imessage" in plan.channels and not past_due,
        "restricted_reason": "payment_failed" if past_due else None,
    }


def can_run_action(plan_name: str, action: str, subscription_status: str | None = None) -> bool:
    return True
