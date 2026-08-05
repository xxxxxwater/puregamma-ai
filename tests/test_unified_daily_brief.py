from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from packages.data.earnings_calendar import earnings_for
from packages.data.macro_calendar import events_for
from packages.database.models import DailyBriefPreference, MarketSnapshot, NotificationDelivery, SharedMarketIntelligence, Signal, utcnow
from packages.reports.unified_daily_brief import MAX_IMESSAGE_BYTES, generate_unified_daily_brief
from packages.workers import tasks


def test_macro_and_earnings_calendars_have_known_dates():
    assert any("FOMC" in item for item in events_for(date(2026, 7, 29), "en"))
    assert events_for(date(2026, 7, 29), "zh") == ["FOMC 利率决议日"]
    assert any("CPI" in item for item in events_for(date(2026, 7, 14), "en"))
    assert any("GOOGL" in item for item in earnings_for(date(2026, 7, 21), "en"))
    assert earnings_for(date(2026, 3, 3), "en") == []


def test_generate_unified_brief_bilingual_and_capped(db):
    db.add(MarketSnapshot(asset_id="BTC", price=65491.5, volume_24h=1e9, market_cap=1.3e12, funding_rate=0.0001, open_interest=2e10, timestamp=utcnow()))
    db.add(MarketSnapshot(asset_id="ETH", price=1923.2, volume_24h=5e8, market_cap=2.3e11, funding_rate=0.0001, open_interest=8e9, timestamp=utcnow()))
    db.add(SharedMarketIntelligence(market_regime="Risk-on momentum", summary_markdown="x", source_snapshot_ids=[])
           )
    db.add(Signal(asset="BTC", signal_type="momentum", direction="long", confidence=0.8, risk_score=3, thesis="Trend continuation with ETF inflows", catalyst="ETF", invalidation="55k", timeframe="days"))
    db.commit()

    zh = generate_unified_daily_brief(db, "zh", today=date(2026, 7, 21))
    en = generate_unified_daily_brief(db, "en", today=date(2026, 7, 21))

    assert "每日简报" in zh and "Daily Brief" in en
    assert "$65,492" in zh or "$65,491" in zh
    assert "GOOGL" in zh  # 2026-07-21 is an estimated GOOGL earnings date
    assert "Trend continuation" in en
    assert len(zh.encode("utf-8")) <= MAX_IMESSAGE_BYTES
    assert len(en.encode("utf-8")) <= MAX_IMESSAGE_BYTES
    assert "使用该服务用户自行承担风险" in zh
    assert "Users bear all risks" in en


def test_generate_unified_brief_survives_empty_database(db):
    brief = generate_unified_daily_brief(db, "zh", today=date(2026, 1, 5))
    assert "每日简报" in brief
    assert len(brief.encode("utf-8")) <= MAX_IMESSAGE_BYTES


def test_broadcast_wrapper_delegates_to_orchestrator_idempotently(monkeypatch, db, demo_user):
    """send_unified_daily_brief_to_all is now a thin wrapper: no separate
    broadcast chain, no unified-brief deliveries — exactly one dispatch path."""
    db.add(
        DailyBriefPreference(
            user_id=demo_user.id,
            enabled=True,
            channel="email",
            locale="en",
            timezone="UTC",
            local_time="08:00",
            next_delivery_at=utcnow() - timedelta(minutes=1),
            recipient=demo_user.email,
        )
    )
    db.commit()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    first = tasks.send_unified_daily_brief_to_all.run()
    second = tasks.send_unified_daily_brief_to_all.run()

    assert first["due"] == 1
    assert first["failed"] == 0
    assert second["due"] == 0  # no re-dispatch on rerun
    deliveries = db.query(NotificationDelivery).filter(
        NotificationDelivery.idempotency_key.like("daily-brief:%")
    ).all()
    assert deliveries  # orchestrator deliveries exist
    assert len({row.idempotency_key for row in deliveries}) == len(deliveries)
    assert db.query(NotificationDelivery).filter(
        NotificationDelivery.idempotency_key.like("unified-brief:%")
    ).count() == 0  # the legacy broadcast chain is gone
