from datetime import datetime, timedelta, timezone

from apps.api.services.daily_push_service import next_delivery
from packages.database.models import DailyBriefPreference, NotificationDelivery, Report, utcnow
from packages.workers import tasks
from tests.conftest import auth_headers


def test_next_delivery_uses_iana_timezone():
    now = datetime(2026, 7, 12, 0, 0, tzinfo=timezone.utc)

    scheduled = next_delivery("Asia/Shanghai", "09:30", now)

    assert scheduled == datetime(2026, 7, 12, 1, 30, tzinfo=timezone.utc)


def test_free_user_cannot_enable_imessage_via_api(api_client, normal_user):
    response = api_client.put(
        "/notifications/preferences/daily-brief",
        json={"enabled": True, "channel": "imessage", "timezone": "Asia/Shanghai", "local_time": "09:30"},
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CHANNEL_ENTITLEMENT_DENIED"


def test_daily_push_preference_is_persisted_with_next_delivery(api_client, pro_user):
    response = api_client.put(
        "/notifications/preferences/daily-brief",
        json={"enabled": True, "channel": "telegram", "timezone": "Asia/Shanghai", "local_time": "09:30", "include_sentiment": True},
        headers=auth_headers(pro_user),
    )

    assert response.status_code == 200
    preference = response.json()["preference"]
    assert preference["channel"] == "telegram"
    assert preference["next_delivery_at"]
    assert preference["include_sentiment"] is True


def test_due_daily_push_reuses_report_and_is_idempotent(monkeypatch, db, pro_user):
    user_id = pro_user.id
    pro_user.preference.include_portfolio_in_ai = False
    row = DailyBriefPreference(user_id=pro_user.id, enabled=True, timezone="UTC", local_time="08:30", channel="email", locale="en", next_delivery_at=utcnow() - timedelta(minutes=1), recipient=pro_user.email)
    db.add(row)
    db.commit()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    first = tasks.dispatch_due_daily_briefs.run()
    second = tasks.dispatch_due_daily_briefs.run()

    assert first["due"] == 1
    assert second["due"] == 0
    assert db.query(Report).filter_by(user_id=user_id, report_type="daily_market_report").count() == 1
    assert db.query(NotificationDelivery).filter_by(user_id=user_id, channel="email").count() == 1
