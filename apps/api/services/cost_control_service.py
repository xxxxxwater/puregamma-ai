from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy.orm import Session

from apps.api.services.entitlement_service import get_user_entitlement
from packages.database.models import Report, User


class DailyLimitExceededError(RuntimeError):
    pass


def day_start() -> datetime:
    return datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)


def cached_daily_report(db: Session, user_id: str, language: str = "en") -> Report | None:
    return (
        db.query(Report)
        .filter(
            Report.user_id == user_id,
            Report.report_type == "daily_market_report",
            Report.language == language,
            Report.created_at >= day_start(),
        )
        .order_by(Report.created_at.desc())
        .first()
    )


def assert_daily_report_limit(db: Session, user_id: str) -> None:
    user = db.get(User, user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")
    entitlement = get_user_entitlement(db, user_id)
    limit = entitlement["max_daily_reports"]
    used = (
        db.query(Report)
        .filter(
            Report.user_id == user_id,
            Report.report_type == "daily_market_report",
            Report.created_at >= day_start(),
        )
        .count()
    )
    if used >= limit:
        raise DailyLimitExceededError(
            f"Daily report limit reached for plan {entitlement['plan']}"
        )
