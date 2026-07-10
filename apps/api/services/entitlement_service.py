from __future__ import annotations

from sqlalchemy.orm import Session

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
    return entitlement_for_plan(user.plan, active_subscription_status(db, user_id))


def assert_action_allowed(db: Session, user_id: str, action: str) -> None:
    user = db.get(User, user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")
    status = active_subscription_status(db, user_id)
    if not can_run_action(user.plan, action, status):
        raise EntitlementDeniedError(f"{action} is not allowed for plan={user.plan} status={status}")
