"""Integration tests for the /api/research endpoints (P0-1)."""
from __future__ import annotations

from datetime import timedelta

from apps.api.services import research_event_service
from packages.data import earnings_calendar
from packages.database.models import MarketEvent, utcnow
from packages.workers import tasks
from tests.conftest import auth_headers


def test_today_requires_authentication(api_client):
    response = api_client.get("/api/research/today")
    assert response.status_code == 401


def test_today_contract_keys(api_client, demo_user):
    response = api_client.get("/api/research/today", headers=auth_headers(demo_user))
    assert response.status_code == 200
    payload = response.json()
    for key in (
        "as_of",
        "timezone",
        "overnight_events",
        "portfolio_impacts",
        "actions",
        "next_event",
        "health",
        "locale",
    ):
        assert key in payload
    assert payload["timezone"] == "UTC"
    assert payload["locale"] == "en"
    assert isinstance(payload["overnight_events"], list)
    assert isinstance(payload["portfolio_impacts"], list)
    assert isinstance(payload["actions"], list)
    assert payload["health"]["overall"] in {"ok", "degraded"}
    # No snapshot has been built: explicit empty content, degraded health.
    assert payload["overnight_events"] == []
    assert payload["health"]["note"] == "no_research_snapshot"


def test_today_locale_query_param(api_client, demo_user):
    response = api_client.get("/api/research/today?locale=zh", headers=auth_headers(demo_user))
    assert response.status_code == 200
    assert response.json()["locale"] == "zh"


def _confirmed_rows():
    report_day = (utcnow() + timedelta(days=2)).date().isoformat()
    return [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "time_label": "time-after-hours",
            "eps_forecast": "$1.42",
            "market_cap": "$3.2T",
            "source_url": earnings_calendar.NASDAQ_EARNINGS_PAGE_URL,
            "as_of": report_day,
            "confirmed": True,
        }
    ]


def test_upcoming_events_and_task_rerun_idempotent(api_client, db, demo_user, monkeypatch):
    monkeypatch.setattr(
        earnings_calendar, "upcoming_confirmed_earnings", lambda start_day, days=7: _confirmed_rows()
    )
    monkeypatch.setattr(research_event_service, "_fetch_deribit_metrics", lambda: None)
    # Run the celery task body against the in-memory test database. The task
    # closes the session, so mint the token before invoking it.
    headers = auth_headers(demo_user)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    first = tasks.build_research_events()
    assert first["snapshot_id"]
    count_after_first = db.query(MarketEvent).count()
    assert count_after_first > 0

    second = tasks.build_research_events()
    assert db.query(MarketEvent).count() == count_after_first
    assert second["events"] == {}

    response = api_client.get("/api/research/events/upcoming", headers=headers)
    assert response.status_code == 200
    events = response.json()["events"]
    earnings = [event for event in events if event["event_type"] == "earnings_confirmed"]
    assert earnings, "confirmed earnings event should be listed"
    apple = next(event for event in earnings if "AAPL" in event["assets"])
    assert apple["source"]["provider"] == "nasdaq_earnings_calendar"
    assert apple["source"]["url"] == earnings_calendar.NASDAQ_EARNINGS_PAGE_URL
    for key in (
        "id",
        "event_type",
        "title",
        "summary",
        "source",
        "collected_at",
        "data_cutoff_at",
        "freshness_minutes",
        "assets",
        "impacts",
        "confidence",
        "evidence_gaps",
    ):
        assert key in apple

    today = api_client.get("/api/research/today", headers=headers).json()
    assert today["next_event"] is not None
    assert today["next_event"]["event_type"] in {"earnings_confirmed", "macro_scheduled"}


def test_overnight_portfolio_impact_opportunities_alerts_endpoints(api_client, demo_user, monkeypatch):
    monkeypatch.setattr(research_event_service, "_fetch_deribit_metrics", lambda: None)
    # Keep the Deribit public API offline; the endpoint must degrade, not hang.
    monkeypatch.setattr(
        "apps.api.services.options_service.get_option_chain",
        lambda currency: {"status": "DEGRADED", "error": "offline", "instruments": []},
    )
    for path in (
        "/api/research/overnight",
        "/api/research/portfolio/impact",
        "/api/research/opportunities",
        "/api/research/alerts",
    ):
        response = api_client.get(path, headers=auth_headers(demo_user))
        assert response.status_code == 200, path
        assert response.json()["as_of"], path
