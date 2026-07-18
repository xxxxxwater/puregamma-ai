from __future__ import annotations

from packages.workers.scheduler import build_scheduler


def test_scheduler_registers_required_jobs():
    scheduler = build_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}

    assert {
        "shared_daily_market_intelligence",
        "personalized_daily_reports",
        "market_anomaly_scan",
        "funding_oi_scan",
        "market_regime_summary",
        "send_daily_reports",
        "subscription_status_check",
        "provider_binance_market_sync",
    } <= job_ids
