from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy.orm import Session

from packages.billing.plans import get_plan
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
    pass
