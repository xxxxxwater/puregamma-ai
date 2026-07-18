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
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=0, minute=10),
        args=["puregamma.generate_personalized_daily_reports"],
        id="personalized_daily_reports",
    )
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
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=1, minute=0),
        args=["puregamma.check_subscription_status"],
        id="subscription_status_check",
    )
    scheduler.add_job(
        enqueue,
        IntervalTrigger(hours=48),
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
    return scheduler


def main() -> None:
    build_scheduler().start()


if __name__ == "__main__":
    main()
