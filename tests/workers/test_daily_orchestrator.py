"""Unified daily report orchestrator tests (vertical slice P0-8).

Covers the production incident fix (DailyLimitExceededError infinite failure
loop), generic-failure backoff, Scenario-G exactly-once dispatch, scheduled vs
manual daily limits, multi-channel recipient gaps, the report library API, and
the preference serialization contract.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.services import report_service
from apps.api.services.cost_control_service import DailyLimitExceededError
from apps.api.services.daily_push_service import next_delivery
from apps.api.services.report_service import create_daily_report
from packages.database.models import DailyBriefPreference, NotificationDelivery, Report, utcnow
from packages.workers import tasks
from tests.conftest import auth_headers

DEFAULT_TYPES = ("crypto_daily", "us_daily", "week_ahead_events", "portfolio_daily")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _due_preference(db, user, *, channels=None, report_types=None, timezone_name="UTC", local_time="08:30") -> DailyBriefPreference:
    row = DailyBriefPreference(
        user_id=user.id,
        enabled=True,
        timezone=timezone_name,
        local_time=local_time,
        channel=(channels or ["email"])[0],
        channels=channels,
        report_types=report_types,
        locale="en",
        next_delivery_at=utcnow() - timedelta(minutes=1),
        recipient=user.email,
    )
    db.add(row)
    db.commit()
    return row


def _reload(db, user_id: str) -> DailyBriefPreference:
    # The task closes the shared session on exit, so re-query instead of refresh.
    return db.get(DailyBriefPreference, user_id)


# (a) THE INCIDENT: DailyLimitExceededError must be terminal for today, never
# an infinite per-minute failure loop.
def test_daily_limit_error_advances_to_next_slot_without_retry_loop(monkeypatch, db, user_factory):
    user = user_factory("limit-user@puregamma.ai", plan="Pro")
    user_id = user.id
    _due_preference(db, user)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    def raise_limit(*args, **kwargs):
        raise DailyLimitExceededError("Daily report limit reached")

    monkeypatch.setattr(tasks, "create_typed_daily_report", raise_limit)

    first = tasks.dispatch_due_daily_briefs.run()
    preference = _reload(db, user_id)

    expected_slot = next_delivery("UTC", "08:30", utcnow() + timedelta(minutes=1))
    assert first["due"] == 1
    assert first["failed"] == 0
    assert preference.failure_count == 0
    assert preference.last_error == "DAILY_LIMIT"
    assert abs((_aware(preference.next_delivery_at) - expected_slot).total_seconds()) < 120
    assert db.query(Report).filter_by(user_id=user_id).count() == 0
    assert db.query(NotificationDelivery).filter_by(user_id=user_id).count() == 0

    second = tasks.dispatch_due_daily_briefs.run()

    assert second["due"] == 0  # not re-due until the next local slot
    assert db.query(Report).filter_by(user_id=user_id).count() == 0


# (b) Generic failure: backoff 2**failure_count minutes, always advancing.
def test_generic_failure_applies_growing_backoff(monkeypatch, db, user_factory):
    user = user_factory("fail-user@puregamma.ai", plan="Pro")
    user_id = user.id
    _due_preference(db, user)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    def raise_boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "create_typed_daily_report", raise_boom)

    started_first = utcnow()
    first = tasks.dispatch_due_daily_briefs.run()
    preference = _reload(db, user_id)

    assert first["failed"] == 1
    assert preference.failure_count == 1
    assert preference.last_error == "RuntimeError"
    backoff_first = (_aware(preference.next_delivery_at) - started_first).total_seconds()
    assert 2 * 60 - 10 <= backoff_first <= 2 * 60 + 90  # ~2 minutes, never due next minute

    # Force the preference due again to observe the next backoff step.
    preference.next_delivery_at = utcnow() - timedelta(minutes=1)
    db.commit()

    started_second = utcnow()
    second = tasks.dispatch_due_daily_briefs.run()
    preference = _reload(db, user_id)

    assert second["failed"] == 1
    assert preference.failure_count == 2
    backoff_second = (_aware(preference.next_delivery_at) - started_second).total_seconds()
    assert backoff_second > backoff_first
    assert 4 * 60 - 10 <= backoff_second <= 4 * 60 + 90


# (c) Scenario G shape: 8 users due the same minute, exactly-once everywhere.
def test_eight_users_same_minute_exactly_once(monkeypatch, db, user_factory):
    users = [user_factory(f"orch-user-{index}@puregamma.ai", plan="Pro") for index in range(8)]
    user_ids = [user.id for user in users]  # capture before the task closes the session
    for user in users:
        _due_preference(db, user, channels=["email", "telegram"])
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    first = tasks.dispatch_due_daily_briefs.run()
    second = tasks.dispatch_due_daily_briefs.run()

    assert first["due"] == 8
    assert first["failed"] == 0
    assert second["due"] == 0

    reports = db.query(Report).filter(Report.user_id.in_(user_ids)).all()
    report_keys = {(row.user_id, row.report_type, row.report_date.isoformat()) for row in reports}
    assert len(reports) == 8 * len(DEFAULT_TYPES)
    assert len(report_keys) == 8 * len(DEFAULT_TYPES)  # exactly 1 per (user, type, local_date)

    deliveries = db.query(NotificationDelivery).filter(NotificationDelivery.user_id.in_(user_ids)).all()
    per_user_channel = {}
    for row in deliveries:
        per_user_channel[(row.user_id, row.channel)] = per_user_channel.get((row.user_id, row.channel), 0) + 1
    assert len({row.idempotency_key for row in deliveries}) == len(deliveries)
    for user_id in user_ids:
        for channel in ("email", "telegram", "web"):
            # email is a single consolidated mail; other channels keep one
            # notification per report type (024b983).
            expected = 1 if channel == "email" else len(DEFAULT_TYPES)
            assert per_user_channel.get((user_id, channel)) == expected

    reports_after = db.query(Report).filter(Report.user_id.in_(user_ids)).count()
    deliveries_after = db.query(NotificationDelivery).filter(NotificationDelivery.user_id.in_(user_ids)).count()
    assert reports_after == len(reports)
    assert deliveries_after == len(deliveries)  # second run: no duplicates


# (d) Scheduled dispatch must not consume the manual daily-report allowance.
def test_scheduled_dispatch_skips_manual_daily_limit(monkeypatch, db, user_factory):
    user = user_factory("scheduled-user@puregamma.ai", plan="Pro")
    user_id = user.id
    _due_preference(db, user)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    def forbidden(*args, **kwargs):
        raise DailyLimitExceededError("manual allowance must not gate scheduled dispatch")

    monkeypatch.setattr(report_service, "assert_daily_report_limit", forbidden)

    result = tasks.dispatch_due_daily_briefs.run()

    assert result["failed"] == 0
    assert db.query(Report).filter_by(user_id=user_id).count() == len(DEFAULT_TYPES)

    # The manual generation path still enforces the daily limit.
    with pytest.raises(DailyLimitExceededError):
        create_daily_report(db, user_id, "en")


# (e) A channel without its recipient is skipped with a reason; the run and the
# preference stay healthy.
def test_missing_channel_recipient_is_skipped_not_failed(monkeypatch, db, user_factory):
    user = user_factory("multi-user@puregamma.ai", plan="Max")
    user_id = user.id
    user.preference.slack_webhook_url = None
    _due_preference(db, user, channels=["email", "slack"])
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    result = tasks.dispatch_due_daily_briefs.run()
    preference = _reload(db, user_id)

    assert result["failed"] == 0
    assert preference.enabled is True
    assert preference.failure_count == 0
    assert preference.last_error is None

    email_rows = db.query(NotificationDelivery).filter_by(user_id=user_id, channel="email").all()
    assert len(email_rows) == 1  # single consolidated mail (024b983)
    # No SMTP credentials in tests: mock provider records a skipped delivery.
    assert {row.status for row in email_rows} == {"skipped"}

    slack_rows = db.query(NotificationDelivery).filter_by(user_id=user_id, channel="slack").all()
    assert len(slack_rows) == len(DEFAULT_TYPES)
    assert {row.status for row in slack_rows} == {"skipped"}
    assert {row.provider_response.get("reason") for row in slack_rows} == {"missing_recipient"}

    web_rows = db.query(NotificationDelivery).filter_by(user_id=user_id, channel="web").all()
    assert len(web_rows) == len(DEFAULT_TYPES)
    assert {row.status for row in web_rows} == {"sent"}


# (f) Report library filters, pagination, and per-report delivery statuses.
def test_report_library_filters_pagination_and_deliveries(db, api_client, user_factory):
    user = user_factory("library-user@puregamma.ai", plan="Pro")
    today = utcnow().date()
    yesterday = today - timedelta(days=1)
    report_us = Report(user_id=user.id, title="US Daily", report_type="us_daily", language="en", content_markdown="us", assets=["AAPL"], report_date=today, status="completed", idempotency_key="lib:us:en")
    report_week = Report(user_id=user.id, title="Week Ahead", report_type="week_ahead_events", language="en", content_markdown="week", assets=["MSFT"], report_date=yesterday, status="completed", idempotency_key="lib:week:en")
    report_zh = Report(user_id=user.id, title="美股日报", report_type="us_daily", language="zh", content_markdown="us zh", assets=["TSLA"], report_date=today, status="completed", idempotency_key="lib:us:zh")
    db.add_all([report_us, report_week, report_zh])
    db.flush()
    db.add(
        NotificationDelivery(
            user_id=user.id,
            channel="web",
            recipient=user.id,
            payload={"message": "us", "report_id": report_us.id},
            locale="en",
            status="sent",
            provider_response={"reason": "web_inbox"},
            idempotency_key="lib:delivery:web",
            sent_at=utcnow(),
        )
    )
    db.commit()

    response = api_client.get("/reports?type=us_daily&language=en", headers=auth_headers(user))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert [item["id"] for item in body["reports"]] == [report_us.id]

    by_date = api_client.get(f"/reports?date={yesterday.isoformat()}", headers=auth_headers(user))
    assert by_date.status_code == 200
    assert [item["id"] for item in by_date.json()["reports"]] == [report_week.id]

    by_language = api_client.get("/reports?language=zh", headers=auth_headers(user))
    assert by_language.status_code == 200
    assert [item["id"] for item in by_language.json()["reports"]] == [report_zh.id]

    by_asset = api_client.get("/reports?asset=aapl", headers=auth_headers(user))
    assert by_asset.status_code == 200
    assert [item["id"] for item in by_asset.json()["reports"]] == [report_us.id]

    default_list = api_client.get("/reports", headers=auth_headers(user))
    assert default_list.status_code == 200
    assert default_list.json()["total"] == 2  # legacy resolved-locale default

    detail = api_client.get(f"/reports/{report_us.id}", headers=auth_headers(user))
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["report"]["id"] == report_us.id
    assert len(detail_body["deliveries"]) == 1
    delivery = detail_body["deliveries"][0]
    assert delivery["channel"] == "web"
    assert delivery["status"] == "sent"
    assert delivery["retry_count"] == 0
    assert delivery["last_error"] is None
    assert delivery["sent_at"]


# (g) Preference API exposes the new orchestrator fields.
def test_preference_api_exposes_channels_report_types_and_failure_state(db, api_client, user_factory):
    user = user_factory("pref-user@puregamma.ai", plan="Pro")
    response = api_client.put(
        "/notifications/preferences/daily-brief",
        json={
            "enabled": True,
            "channels": ["email", "telegram"],
            "report_types": ["crypto_daily", "us_daily"],
            "timezone": "Asia/Shanghai",
            "local_time": "09:30",
        },
        headers=auth_headers(user),
    )

    assert response.status_code == 200
    preference = response.json()["preference"]
    assert preference["channels"] == ["email", "telegram"]
    assert preference["channel"] == "email"  # legacy single channel stays in sync
    assert preference["report_types"] == ["crypto_daily", "us_daily"]
    assert preference["failure_count"] == 0
    assert preference["last_error"] is None
    assert preference["next_delivery_at"]

    row = db.get(DailyBriefPreference, user.id)
    row.failure_count = 3
    row.last_error = "RuntimeError"
    db.commit()

    fetched = api_client.get("/notifications/preferences/daily-brief", headers=auth_headers(user))
    assert fetched.status_code == 200
    serialized = fetched.json()["preference"]
    assert serialized["failure_count"] == 3
    assert serialized["last_error"] == "RuntimeError"
    assert serialized["channels"] == ["email", "telegram"]
    assert serialized["report_types"] == ["crypto_daily", "us_daily"]


def test_preference_api_rejects_unentitled_and_unknown_channels(api_client, user_factory):
    free_user = user_factory("free-pref@puregamma.ai", plan="Free")
    denied = api_client.put(
        "/notifications/preferences/daily-brief",
        json={"enabled": True, "channels": ["email", "slack"]},
        headers=auth_headers(free_user),
    )
    assert denied.status_code == 403

    pro_user = user_factory("pro-pref@puregamma.ai", plan="Pro")
    invalid = api_client.put(
        "/notifications/preferences/daily-brief",
        json={"enabled": True, "channels": ["email", "pigeon"]},
        headers=auth_headers(pro_user),
    )
    assert invalid.status_code == 400

    invalid_type = api_client.put(
        "/notifications/preferences/daily-brief",
        json={"report_types": ["crypto_daily", "horoscope"]},
        headers=auth_headers(pro_user),
    )
    assert invalid_type.status_code == 400
