from __future__ import annotations

from packages.workers import tasks


def test_daily_push_job_sends_only_successful_channels(monkeypatch, db, demo_user):
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    sent = tasks.send_daily_reports_to_channels.run()

    assert sent == 1
