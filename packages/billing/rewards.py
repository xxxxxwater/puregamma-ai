from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from packages.database.models import CreditRewardGrant, User


REWARD_CAPS = {
    "welcome_grant": (1_000, 1_000, 1_000),
    "onboarding_portfolio_grant": (200, 200, 200),
    "daily_brief_feedback_grant": (20, 100, 300),
    "streak_grant": (50, 100, 500),
    "referral_grant": (200, 400, 1_000),
    "bug_bounty_grant": (1_000, 2_000, 5_000),
    "manual_admin_grant": (5_000, 10_000, 30_000),
}


def grant_reward(
    db: Session,
    user_id: str,
    reward_type: str,
    credits: int,
    *,
    idempotency_key: str,
    source: str,
    metadata: dict | None = None,
    granted_by_user_id: str | None = None,
) -> CreditRewardGrant:
    from apps.api.services.credit_service import grant_credits

    if reward_type not in REWARD_CAPS:
        raise ValueError("Unsupported reward type")
    if credits <= 0:
        raise ValueError("Reward credits must be positive")
    existing = db.query(CreditRewardGrant).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing:
        return existing
    user = db.query(User).filter(User.id == user_id).with_for_update().one()
    existing = db.query(CreditRewardGrant).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing:
        return existing
    if reward_type == "manual_admin_grant" and not granted_by_user_id:
        raise ValueError("Manual admin grants require an audited administrator")
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(CreditRewardGrant).filter_by(user_id=user.id, reward_type=reward_type).all()
    daily = sum(row.credits for row in rows if row.created_at.replace(tzinfo=row.created_at.tzinfo or timezone.utc) >= day_start)
    monthly = sum(row.credits for row in rows if row.created_at.replace(tzinfo=row.created_at.tzinfo or timezone.utc) >= month_start)
    lifetime = sum(row.credits for row in rows)
    daily_cap, monthly_cap, lifetime_cap = REWARD_CAPS[reward_type]
    if daily + credits > daily_cap or monthly + credits > monthly_cap or lifetime + credits > lifetime_cap:
        raise ValueError("Reward cap exceeded")
    ledger = grant_credits(
        db,
        user.id,
        reward_type,
        credits,
        {**(metadata or {}), "source": source, "granted_by_user_id": granted_by_user_id},
        idempotency_key=f"reward:{idempotency_key}",
    )
    row = CreditRewardGrant(
        user_id=user.id,
        reward_type=reward_type,
        credits=credits,
        source=source,
        idempotency_key=idempotency_key,
        metadata_json=metadata or {},
        granted_by_user_id=granted_by_user_id,
        ledger_entry_id=ledger.id,
    )
    db.add(row)
    db.flush()
    return row
