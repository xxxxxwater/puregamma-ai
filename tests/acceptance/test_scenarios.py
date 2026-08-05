"""Scenario A-K acceptance tests (final verification slice).

See tests/acceptance/README.md for the full scenario -> test map. This file
contains only the scenarios that were NOT already covered elsewhere:

* Scenario A (complement): /api/research/today payload CONTENT — overnight
  events carry source provider/published_at/freshness, actions <= 3,
  next_event present (the key/shape contract is covered in
  tests/integration/test_research_api.py).
* Scenario C (new path): event alert exactly-once via
  research_event_service.create_alert_for_event — 1 Alert, 1 delivery per
  channel, rerun creates zero new rows.
* Scenario F (complement): SSE acceptance — first event byte on the fast-path
  agent stream in < 2s (measures accept+plan, not LLM latency).
* Scenario K (new, opt-in load): 300 users due the same minute, orchestrator
  rerun exactly-once, wall time, failure_count <= 1. Skipped unless
  ``--runload`` is passed (see tests/acceptance/conftest.py).
"""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from sqlalchemy import func

from apps.api.config import Settings
from apps.api.services import agent_answer_service, agent_service, daily_report_renderers, research_event_service
from packages.agents.llm.schemas import LLMStreamChunk
from packages.data import earnings_calendar
from packages.database.models import (
    AccountSnapshot,
    Alert,
    DailyBriefPreference,
    ExchangeConnection,
    MarketEvent,
    MarketQuoteRecord,
    NotificationDelivery,
    PositionSnapshot,
    Report,
    TradingAccount,
    User,
    UserPreference,
    utcnow,
)
from packages.workers import tasks
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Shared seeding helpers (kept local: acceptance tests must not import other
# test modules under --import-mode=importlib).
# ---------------------------------------------------------------------------


def _quote(symbol: str, base: str, pct: float | None, *, age_minutes: float = 5) -> MarketQuoteRecord:
    now = utcnow()
    return MarketQuoteRecord(
        symbol=symbol,
        base_asset=base,
        quote_asset="USDT",
        asset_type="spot",
        provider="binance",
        price=100.0,
        change_24h_pct=pct,
        source_timestamp=now - timedelta(minutes=age_minutes),
        fetched_at=now - timedelta(minutes=age_minutes),
        provenance_json={"provider": "binance", "source_url": "https://api.binance.com/api/v3/ticker/24hr"},
    )


def _synthetic_holdings(db, user) -> None:
    captured = utcnow()
    account = TradingAccount(
        user_id=user.id,
        name="Synthetic Hyperliquid",
        venue="HYPERLIQUID",
        account_type="READ_ONLY",
        base_currency="USD",
        status="ACTIVE",
        permissions_json={"read_positions": True},
    )
    db.add(account)
    db.flush()
    db.add(
        ExchangeConnection(
            user_id=user.id,
            account_id=account.id,
            adapter="hyperliquid",
            environment="production",
            status="CONNECTED",
            metadata_json={"wallet_address": "0x" + "a" * 40},
        )
    )
    db.add(
        AccountSnapshot(
            user_id=user.id,
            account_id=account.id,
            balance=10_000.0,
            equity=10_000.0,
            available_margin=5_000.0,
            daily_pnl=0.0,
            drawdown=0.0,
            exposure=5_000.0,
            stale=False,
            raw_event_reference={"provider": "hyperliquid", "payload": {}},
            captured_at=captured,
        )
    )
    db.add(
        PositionSnapshot(
            user_id=user.id,
            account_id=account.id,
            instrument="BTC",
            quantity=0.1,
            side="LONG",
            average_price=45_000.0,
            mark_price=50_000.0,
            unrealized_pnl=500.0,
            realized_pnl=0.0,
            leverage=1.0,
            raw_event_reference={"provider": "hyperliquid", "value": 5_000.0},
            captured_at=captured,
        )
    )
    db.commit()


def _offline_research_providers(monkeypatch):
    monkeypatch.setattr(research_event_service, "_fetch_deribit_metrics", lambda: None)


# ---------------------------------------------------------------------------
# Scenario A — /api/research/today payload content (complements
# tests/integration/test_research_api.py, which covers keys/auth/next_event).
# ---------------------------------------------------------------------------


def test_scenario_a_today_payload_content(api_client, db, demo_user, monkeypatch):
    _offline_research_providers(monkeypatch)
    report_day = (utcnow() + timedelta(days=2)).date().isoformat()
    monkeypatch.setattr(
        earnings_calendar,
        "upcoming_confirmed_earnings",
        lambda start_day, days=7: [
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
        ],
    )
    db.add(_quote("BTCUSDT", "BTC", 7.5))
    db.commit()

    snapshot = research_event_service.build_research_events(db, "intraday", 24)
    research_event_service.compute_asset_impacts(db, snapshot)
    research_event_service.compute_user_portfolio_impacts(db, snapshot)

    response = api_client.get("/api/research/today", headers=auth_headers(demo_user))
    assert response.status_code == 200
    payload = response.json()

    events = payload["overnight_events"]
    assert events, "expected stored overnight events"
    for event in events:
        source = event["source"]
        assert source["provider"], event["title"]
        assert source["published_at"], event["title"]
        assert event["freshness_minutes"] is not None
        assert event["freshness_minutes"] >= 0

    assert len(payload["actions"]) <= 3

    next_event = payload["next_event"]
    assert next_event is not None
    assert next_event["event_type"] in {"earnings_confirmed", "macro_scheduled"}
    assert next_event["scheduled_at"]
    assert next_event["source"]["provider"]


# ---------------------------------------------------------------------------
# Scenario C — event alert exactly-once (NEW path:
# research_event_service.create_alert_for_event).
# ---------------------------------------------------------------------------


def test_scenario_c_event_alert_exactly_once(db, user_factory, monkeypatch):
    _offline_research_providers(monkeypatch)
    monkeypatch.setattr(earnings_calendar, "upcoming_confirmed_earnings", lambda start_day, days=7: [])
    user = user_factory("scenario-c-alert@puregamma.ai", plan="Max", credit_balance=10_000)
    _synthetic_holdings(db, user)
    db.add(_quote("BTCUSDT", "BTC", 7.5))
    db.commit()

    snapshot = research_event_service.build_research_events(db, "intraday", 24)
    research_event_service.compute_asset_impacts(db, snapshot)
    impacts = research_event_service.compute_user_portfolio_impacts(db, snapshot)
    assert impacts["created"] >= 1  # the user's BTC holding is linked to the event

    event = (
        db.query(MarketEvent)
        .filter(MarketEvent.event_type == "price_move", MarketEvent.research_snapshot_id == snapshot.id)
        .one()
    )
    channels = ["email", "telegram", "web"]

    first = research_event_service.create_alert_for_event(db, event, channels=channels)
    assert first == {"users": 1, "alerts": 1, "deliveries": 3}

    alerts = db.query(Alert).filter(Alert.user_id == user.id).all()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.asset == "BTC"
    assert alert.severity == "high"  # confidence 0.9 fresh price move
    assert alert.idempotency_key == f"event-alert:{user.id}:{event.id}"
    assert alert.status == "sent"
    assert alert.sent_at is not None

    deliveries = db.query(NotificationDelivery).filter(NotificationDelivery.user_id == user.id).all()
    assert len(deliveries) == 3
    assert {row.channel for row in deliveries} == {"email", "telegram", "web"}
    assert {row.status for row in deliveries} == {"sent"}
    for row in deliveries:
        assert row.idempotency_key == f"event-alert:{user.id}:{event.id}:{row.channel}"

    # Rerun the alert generation path: zero new rows.
    second = research_event_service.create_alert_for_event(db, event, channels=channels)
    assert second == {"users": 1, "alerts": 0, "deliveries": 0}
    assert db.query(Alert).filter(Alert.user_id == user.id).count() == 1
    assert db.query(NotificationDelivery).filter(NotificationDelivery.user_id == user.id).count() == 3


# ---------------------------------------------------------------------------
# Scenario F (complement) — SSE acceptance: first event byte < 2s on the
# fast-path agent stream with a monkeypatched provider. Measures the
# accept+plan path, not LLM latency.
# ---------------------------------------------------------------------------


class _EchoProvider:
    """Offline provider that echoes the phrasing prompt back instantly."""

    provider_name = "mock"
    model = "echo-model"
    configured = True
    last_error = None

    def stream_chat(self, messages, **kwargs):
        payload = "\n".join(message.content for message in messages)
        yield LLMStreamChunk(delta=payload[:8000], provider="mock", model="echo-model")
        yield LLMStreamChunk(done=True, provider="mock", model="echo-model", prompt_tokens=64, completion_tokens=256)


def test_scenario_sse_first_event_under_two_seconds(api_client, db, pro_user, monkeypatch):
    settings = Settings(enable_mock_agent=True, llm_provider="mock", agent_model="echo-model")
    monkeypatch.setattr(agent_service, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_service, "get_agent_llm_provider", lambda selected_model=None: _EchoProvider())
    monkeypatch.setattr(agent_answer_service, "get_settings", lambda: settings)

    created = api_client.post(
        "/api/agent/conversations",
        json={"title": "sse-acceptance"},
        headers=auth_headers(pro_user),
    )
    conversation_id = created.json()["conversation"]["id"]

    started = time.perf_counter()
    first_event_elapsed = None
    body = bytearray()
    with api_client.stream(
        "POST",
        f"/api/agent/conversations/{conversation_id}/messages",
        json={"content": "隔夜有什么重要的事？", "locale": "zh"},
        headers=auth_headers(pro_user),
    ) as response:
        assert response.status_code == 200
        for chunk in response.iter_bytes():
            if first_event_elapsed is None and chunk:
                first_event_elapsed = time.perf_counter() - started
            body.extend(chunk)

    assert first_event_elapsed is not None, "no SSE bytes received"
    text = body.decode()
    assert "event: run.started" in text
    assert "event: plan.ready" in text
    print(f"\nsse_first_event_seconds={first_event_elapsed:.3f}")
    assert first_event_elapsed < 2.0


# ---------------------------------------------------------------------------
# Scenario K — scale smoke (OPT-IN: skipped unless --runload).
#
# 300 users due at the same minute; LLM renderers monkeypatched to return
# instantly; the orchestrator runs until the due set drains, then once more
# to prove exactly-once.
#
# DEVIATION from the "run TWICE" wording: the production orchestrator caps a
# single run at 100 due preferences (batch safety), so 300 users drain in
# 3 waves + 1 empty verification pass; the explicit rerun below is the
# exactly-once pass. Assertions (a)-(d) hold regardless.
# ---------------------------------------------------------------------------

SCALE_USER_COUNT = 300


@pytest.mark.load
def test_scenario_k_scale_smoke_300_users_same_minute(monkeypatch, db):
    due_at = utcnow() - timedelta(minutes=1)
    users = [
        User(
            email=f"scale-user-{index}@puregamma.ai",
            name=f"scale-user-{index}",
            role="user",
            plan="Pro",
            credit_balance=1_000,
        )
        for index in range(SCALE_USER_COUNT)
    ]
    db.add_all(users)
    db.flush()
    user_ids = [user.id for user in users]
    db.add_all(
        UserPreference(
            user_id=user.id,
            email_recipient=user.email,
            telegram_chat_id="mock-telegram-chat",
            notification_channels=["email"],
        )
        for user in users
    )
    db.add_all(
        DailyBriefPreference(
            user_id=user.id,
            enabled=True,
            timezone="UTC",
            local_time="08:30",
            channel="email",
            channels=["email"],
            report_types=None,  # all four default typed reports
            locale="en",
            next_delivery_at=due_at,
            recipient=user.email,
        )
        for user in users
    )
    db.commit()

    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    # LLM renderers return instantly; everything else (research events,
    # deterministic renderers, credit reserve/settle, channel dispatch) runs
    # the real production path.
    monkeypatch.setattr(
        daily_report_renderers,
        "generate_daily_brief",
        lambda db_, user_id, language: "# PureGamma Daily Brief\n\nDeterministic load-smoke render.",
    )

    report_types = list(tasks.DEFAULT_DAILY_REPORT_TYPES)
    started = time.perf_counter()
    waves = 0
    while True:
        result = tasks.dispatch_due_daily_briefs.run()
        waves += 1
        assert result["failed"] == 0, result
        if result["due"] == 0:
            break
        assert waves < 10, f"orchestrator did not drain within 10 waves: {result}"
    drain_wall = time.perf_counter() - started
    print(f"\nscenario_k: users={SCALE_USER_COUNT} waves={waves} drain_wall_seconds={drain_wall:.2f}")
    # Generous ceiling: expect seconds, never hard-fail below 15 minutes.
    assert drain_wall < 15 * 60

    reports_before = db.query(Report).filter(Report.user_id.in_(user_ids)).count()
    deliveries_before = db.query(NotificationDelivery).filter(NotificationDelivery.user_id.in_(user_ids)).count()

    # Second pass: exactly-once — nothing due, zero new rows.
    rerun_wall_start = time.perf_counter()
    rerun = tasks.dispatch_due_daily_briefs.run()
    assert rerun["due"] == 0
    assert rerun["failed"] == 0
    assert db.query(Report).filter(Report.user_id.in_(user_ids)).count() == reports_before
    assert db.query(NotificationDelivery).filter(NotificationDelivery.user_id.in_(user_ids)).count() == deliveries_before
    print(f"scenario_k: rerun_wall_seconds={time.perf_counter() - rerun_wall_start:.2f}")

    # (a) exactly one Report per (user, type, local_date)
    reports = db.query(Report).filter(Report.user_id.in_(user_ids)).all()
    expected_reports = SCALE_USER_COUNT * len(report_types)
    assert len(reports) == expected_reports
    report_keys = {(row.user_id, row.report_type, row.report_date.isoformat()) for row in reports}
    assert len(report_keys) == expected_reports

    # (b) exactly one NotificationDelivery per (user, channel, type)
    deliveries = db.query(NotificationDelivery).filter(NotificationDelivery.user_id.in_(user_ids)).all()
    assert {row.channel for row in deliveries} == {"email", "web"}
    expected_deliveries = SCALE_USER_COUNT * len(report_types) * 2
    assert len(deliveries) == expected_deliveries
    assert len({row.idempotency_key for row in deliveries}) == len(deliveries)
    per_user_channel_type = {
        (row.user_id, row.channel, row.idempotency_key.split(":")[3]) for row in deliveries
    }
    assert len(per_user_channel_type) == expected_deliveries

    # (c) wall time recorded above (printed); generous ceiling asserted.

    # (d) no user retried more than once
    max_failures = (
        db.query(func.max(DailyBriefPreference.failure_count))
        .filter(DailyBriefPreference.user_id.in_(user_ids))
        .scalar()
    )
    assert (max_failures or 0) <= 1
