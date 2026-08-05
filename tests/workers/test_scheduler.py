from __future__ import annotations

from packages.workers.scheduler import build_scheduler


def test_scheduler_registers_required_jobs():
    scheduler = build_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}

    # Single-orchestrator invariant: the legacy parallel daily chains
    # (unified_daily_brief_broadcast, personalized_daily_reports) are no longer
    # scheduled; only the 00:00 warm and the every-minute orchestrator remain.
    assert "unified_daily_brief_broadcast" not in job_ids
    assert "personalized_daily_reports" not in job_ids
    assert {
        "shared_daily_market_intelligence",
        "market_anomaly_scan",
        "funding_oi_scan",
        "market_regime_summary",
        "send_daily_reports",
        "subscription_status_check",
        "portfolio_autopilot_account_sync",
        "portfolio_nav_sync",
    } <= job_ids
