from __future__ import annotations

from datetime import timedelta

from packages.database.models import DailyBriefPreference, NotificationDelivery, utcnow
from packages.workers import tasks


def test_daily_push_job_delegates_to_unified_orchestrator(monkeypatch, db, demo_user):
    """send_daily_reports_to_channels is a thin wrapper: it warms shared
    intelligence and runs the single per-user dispatch orchestrator."""
    db.add(
        DailyBriefPreference(
            user_id=demo_user.id,
            enabled=True,
            timezone="UTC",
            local_time="08:30",
            channel="email",
            locale="en",
            next_delivery_at=utcnow() - timedelta(minutes=1),
            recipient=demo_user.email,
        )
    )
    db.commit()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    result = tasks.send_daily_reports_to_channels.run()
    again = tasks.send_daily_reports_to_channels.run()

    assert result["due"] == 1
    assert result["failed"] == 0
    assert result["sent"] >= 1
    assert again["due"] == 0  # advanced to the next local slot, no re-dispatch
    email_rows = db.query(NotificationDelivery).filter_by(user_id=demo_user.id, channel="email").all()
    assert len(email_rows) == 4  # one per default report type
    assert {row.status for row in email_rows} == {"sent"}
