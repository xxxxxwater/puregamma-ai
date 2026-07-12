from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.billing.entitlements import can_run_action, entitlement_for_plan
from packages.database.models import Subscription, User


class EntitlementDeniedError(RuntimeError):
    pass


def active_subscription_status(db: Session, user_id: str) -> str | None:
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )
    return sub.status if sub else None


def get_user_entitlement(db: Session, user_id: str) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")
    status = active_subscription_status(db, user_id)
    plan_name = user.plan
    if get_settings().billing_mode == "stripe" and plan_name not in {"Free", "Enterprise"} and status not in {"active", "trialing"}:
        plan_name = "Free"
    return entitlement_for_plan(plan_name, status)


def assert_action_allowed(db: Session, user_id: str, action: str) -> None:
    if not get_settings().entitlements_enforced:
        return
    user = db.get(User, user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")
    status = active_subscription_status(db, user_id)
    if not can_run_action(user.plan, action, status):
        raise EntitlementDeniedError(
            f"Action '{action}' is not available for plan {get_plan_name(user.plan)}"
        )


def get_plan_name(plan_name: str) -> str:
    return entitlement_for_plan(plan_name)["plan"]
