from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from packages.database.models import CreditBudgetPolicy, CreditReservationRecord, User


class AutomationBudgetExceeded(RuntimeError):
    pass


PLAN_DEFAULTS = {
    "Free": (20, 300, 20),
    "Invite Preview": (40, 600, 40),
    "Pro": (150, 1_500, 80),
    "Max": (500, 6_000, 150),
    "Enterprise": (2_000, 30_000, 500),
}

NEXT_ESTIMATED_CREDITS = {
    "daily_brief": 8,
    "daily_brief_delivery": 1,
    "daily_report": 8,
    "daily_report_delivery": 10,
    "portfolio_monitor": 3,
    "paper_monitor": 3,
    "imessage": 2,
    "email": 1,
    "telegram": 1,
}


def _period_starts() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return (
        now.replace(hour=0, minute=0, second=0, microsecond=0),
        now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    )


def get_or_create_policy(db: Session, user: User, automation_key: str) -> CreditBudgetPolicy:
    row = (
        db.query(CreditBudgetPolicy)
        .filter_by(user_id=user.id, automation_key=automation_key)
        .one_or_none()
    )
    if row:
        return row
    daily, monthly, per_run = PLAN_DEFAULTS.get(user.plan, PLAN_DEFAULTS["Free"])
    row = CreditBudgetPolicy(
        user_id=user.id,
        automation_key=automation_key[:120],
        daily_limit=daily,
        monthly_limit=monthly,
        per_run_limit=per_run,
        alert_threshold_pct=80,
    )
    db.add(row)
    db.flush()
    return row


def budget_usage(db: Session, user_id: str, automation_key: str) -> tuple[int, int]:
    day_start, month_start = _period_starts()
    rows = (
        db.query(CreditReservationRecord)
        .filter(
            CreditReservationRecord.user_id == user_id,
            CreditReservationRecord.created_at >= month_start,
            CreditReservationRecord.status.in_(["RESERVED", "SETTLED", "SETTLED_CAPPED"]),
        )
        .all()
    )
    matching = [row for row in rows if (row.metadata_json or {}).get("automation_key") == automation_key]
    monthly = sum(row.settled_credits if row.settled_credits is not None else row.reserved_credits for row in matching)
    daily = sum(
        row.settled_credits if row.settled_credits is not None else row.reserved_credits
        for row in matching
        if row.created_at.replace(tzinfo=row.created_at.tzinfo or timezone.utc) >= day_start
    )
    return daily, monthly


def assert_automation_budget(db: Session, user_id: str, automation_key: str, credits: int) -> CreditBudgetPolicy:
    user = db.query(User).filter(User.id == user_id).with_for_update().one()
    policy = get_or_create_policy(db, user, automation_key)
    daily_used, monthly_used = budget_usage(db, user_id, automation_key)
    reason = None
    if not policy.enabled or policy.paused:
        reason = policy.pause_reason or "AUTOMATION_BUDGET_PAUSED"
    elif credits > policy.per_run_limit:
        reason = "AUTOMATION_PER_RUN_LIMIT"
    elif daily_used + credits > policy.daily_limit:
        reason = "AUTOMATION_DAILY_BUDGET"
    elif monthly_used + credits > policy.monthly_limit:
        reason = "AUTOMATION_MONTHLY_BUDGET"
    if reason:
        policy.paused = True
        policy.pause_reason = reason
        db.flush()
        raise AutomationBudgetExceeded(reason)
    return policy


def pause_automation_budget(db: Session, user_id: str, automation_key: str, reason: str) -> CreditBudgetPolicy:
    """Persist a budget pause after a caller has rolled back a failed run."""
    user = db.query(User).filter(User.id == user_id).with_for_update().one()
    policy = get_or_create_policy(db, user, automation_key)
    policy.paused = True
    policy.pause_reason = reason[:120]
    db.flush()
    return policy


def budget_snapshot(db: Session, user: User) -> list[dict]:
    rows = db.query(CreditBudgetPolicy).filter_by(user_id=user.id).order_by(CreditBudgetPolicy.automation_key).all()
    result = []
    for row in rows:
        daily_used, monthly_used = budget_usage(db, user.id, row.automation_key)
        result.append({
            "automation_key": row.automation_key,
            "daily_limit": row.daily_limit,
            "monthly_limit": row.monthly_limit,
            "per_run_limit": row.per_run_limit,
            "daily_used": daily_used,
            "monthly_used": monthly_used,
            "next_estimated_credits": NEXT_ESTIMATED_CREDITS.get(row.automation_key),
            "alert_threshold_pct": row.alert_threshold_pct,
            "enabled": row.enabled,
            "paused": row.paused,
            "pause_reason": row.pause_reason,
        })
    return result
