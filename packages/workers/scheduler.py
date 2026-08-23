from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from apps.api.config import get_settings
from packages.workers.celery_app import celery_app


def enqueue(task_name: str, *args) -> None:
    """Publish work to Celery; the scheduler process never executes heavy jobs."""
    celery_app.send_task(task_name, args=list(args))


def build_scheduler() -> BlockingScheduler:
    settings = get_settings()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=0, minute=0),
        args=["puregamma.generate_shared_daily_market_intelligence"],
        id="shared_daily_market_intelligence",
    )
    # SINGLE-ORCHESTRATOR INVARIANT: puregamma.dispatch_due_daily_briefs is the
    # only per-user daily dispatch path. The legacy parallel chains
    # (unified_daily_brief_broadcast, personalized_daily_reports) were removed
    # from the schedule; their Celery task names remain registered as thin
    # wrappers that delegate to the orchestrator. Keeping both the 00:00 warm
    # and the every-minute orchestrator is sufficient.
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=15),
        args=["puregamma.scan_market_anomalies"],
        id="market_anomaly_scan",
    )
    scheduler.add_job(
        enqueue, IntervalTrigger(hours=1), args=["puregamma.scan_market_anomalies"], id="funding_oi_scan"
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(hours=4),
        args=["puregamma.generate_shared_daily_market_intelligence"],
        id="market_regime_summary",
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=1),
        args=["puregamma.dispatch_due_daily_briefs"],
        id="send_daily_reports",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=15),
        args=["puregamma.recover_stale_credit_reservations"],
        id="recover_stale_credit_reservations",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=1),
        args=["puregamma.retry_notification_deliveries"],
        id="retry_notification_deliveries",
        max_instances=1,
        coalesce=True,
    )
    # Photon inbound crash/retry recovery (no-op until IMESSAGE_PROVIDER=photon).
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=1),
        args=["puregamma.reap_photon_inbound_tasks"],
        id="photon_inbound_reaper",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=1, minute=0),
        args=["puregamma.check_subscription_status"],
        id="subscription_status_check",
    )
    scheduler.add_job(
        enqueue,
        CronTrigger(
            day_of_week="mon-fri",
            hour=9,
            minute=35,
            timezone="America/New_York",
        ),
        args=["puregamma.refresh_earnings_gamma_candidates"],
        id="earnings_gamma_refresh",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=15),
        args=["puregamma.sync_portfolio_autopilot_accounts"],
        id="portfolio_autopilot_account_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=0, minute=5),
        args=["puregamma.generate_portfolio_nav"],
        id="portfolio_nav_snapshot",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(seconds=settings.nautilus_runtime_sync_interval_seconds),
        args=["puregamma.sync_nautilus_runtime_runs"],
        id="nautilus_runtime_run_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(seconds=settings.nautilus_runtime_sync_interval_seconds),
        args=["puregamma.sync_nautilus_paper_accounts"],
        id="nautilus_paper_account_sync",
        max_instances=1,
        coalesce=True,
    )
    # --- LIVE Trading Control Plane (each job is a cheap no-op when no LIVE
    #     mandate exists; intervals respect the single-server budget) --------
    scheduler.add_job(
        enqueue,
        IntervalTrigger(seconds=max(5, settings.live_price_refresh_interval_seconds)),
        args=["puregamma.refresh_live_market_prices"],
        id="live_market_price_refresh",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(seconds=max(5, settings.live_order_sync_interval_seconds)),
        args=["puregamma.sync_live_order_statuses"],
        id="live_order_status_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(seconds=max(30, settings.live_balance_sync_interval_seconds)),
        args=["puregamma.sync_live_balances_and_positions"],
        id="live_balance_position_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(seconds=max(30, settings.live_nav_calc_interval_seconds)),
        args=["puregamma.calc_nav_for_active_accounts"],
        id="live_nav_calculation",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=max(0, min(23, settings.live_reconciliation_hour_utc)), minute=30),
        args=["puregamma.daily_live_reconciliation"],
        id="live_daily_reconciliation",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=settings.nautilus_reconcile_interval_minutes),
        args=["puregamma.reconcile_active_trading_accounts"],
        id="nautilus_account_reconciliation",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(seconds=settings.nautilus_market_refresh_interval_seconds),
        args=["puregamma.refresh_nautilus_public_market_data"],
        id="nautilus_public_market_refresh",
        max_instances=1,
        coalesce=True,
    )
    if settings.data_sync_worker_enabled:
        if settings.binance_public_data_enabled:
            scheduler.add_job(
                enqueue,
                IntervalTrigger(minutes=1),
                args=["puregamma.sync_data_provider", "binance"],
                id="provider_binance_market_sync",
                max_instances=1,
                coalesce=True,
            )
        scheduler.add_job(
            enqueue,
            IntervalTrigger(minutes=settings.rss_sync_interval),
            args=["puregamma.sync_data_provider", "rss"],
            id="provider_rss_sync",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            enqueue,
            IntervalTrigger(minutes=settings.fintwit_sync_interval),
            args=["puregamma.sync_data_provider", "fintwit"],
            id="provider_fintwit_sync",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            enqueue,
            IntervalTrigger(minutes=settings.x_sync_interval),
            args=["puregamma.sync_data_provider", "x-twitter"],
            id="provider_x_sync",
            max_instances=1,
            coalesce=True,
        )
        if settings.bloomberg_mode in {"mock", "production"}:
            scheduler.add_job(
                enqueue,
                IntervalTrigger(hours=1),
                args=["puregamma.sync_data_provider", "bloomberg"],
                id="provider_bloomberg_sync",
                max_instances=1,
                coalesce=True,
            )
        scheduler.add_job(
            enqueue,
            CronTrigger(hour=2, minute=30),
            args=["puregamma.purge_expired_source_documents"],
            id="provider_retention_cleanup",
            max_instances=1,
            coalesce=True,
        )
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=1, minute=40),
        args=["puregamma.refresh_backtest_lab_candles"],
        id="backtest_lab_candles_refresh",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=5),
        args=["puregamma.refresh_mstr_btc_dashboard"],
        id="mstr_btc_dashboard_refresh",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=15),
        args=["puregamma.build_research_events"],
        id="research_events_build",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=10, minute=5),
        args=["puregamma.sync_earnings_calendar"],
        id="research_earnings_calendar_morning",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=22, minute=5),
        args=["puregamma.sync_earnings_calendar"],
        id="research_earnings_calendar_evening",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        # 03:00 is a product/business-time requirement, not UTC. Making the
        # timezone explicit prevents a container or host timezone change from
        # shifting provider-price approval windows.
        CronTrigger(hour=3, minute=0, timezone="Asia/Shanghai"),
        args=["puregamma.sync_gateway_provider_metadata"],
        id="gateway_provider_metadata_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(minutes=5),
        args=["puregamma.healthcheck_gateway_providers"],
        id="gateway_provider_healthcheck",
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def main() -> None:
    # Single-scheduler invariant: refuse to start if another scheduler holds
    # the lock (fails open when Redis is down; idempotency keys still apply).
    from packages.workers.redis_lock import acquire_redis_lock, release_redis_lock

    if not acquire_redis_lock("scheduler", ttl_seconds=600):
        raise SystemExit(
            "Another scheduler instance holds pg:lock:scheduler; refusing to "
            "start a duplicate (deploy checklist: only one scheduler may run)"
        )
    scheduler = build_scheduler()
    # Keep the lock alive while this process runs; the lock expires naturally
    # if the process dies and a restart can then take over.
    scheduler.add_job(
        acquire_redis_lock,
        IntervalTrigger(minutes=5),
        args=["scheduler"],
        kwargs={"ttl_seconds": 600},
        id="scheduler_lock_renew",
        max_instances=1,
        coalesce=True,
    )
    try:
        scheduler.start()
    finally:
        release_redis_lock("scheduler")


if __name__ == "__main__":
    main()
