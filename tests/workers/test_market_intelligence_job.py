from __future__ import annotations

from packages.database.models import SharedMarketIntelligence
from packages.workers import tasks


def test_market_intelligence_job_generates_shared_record(monkeypatch, db):
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    item_id = tasks.generate_shared_daily_market_intelligence.run()

    assert db.get(SharedMarketIntelligence, item_id) is not None


def test_market_anomaly_scan_returns_signal_count(monkeypatch, db):
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)

    count = tasks.scan_market_anomalies.run()

    assert count >= 1
