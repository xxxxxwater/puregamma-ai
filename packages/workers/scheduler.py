from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from packages.workers import tasks
from apps.api.config import get_settings


def build_scheduler() -> BlockingScheduler:
    settings = get_settings()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        tasks.generate_shared_daily_market_intelligence,
        CronTrigger(hour=0, minute=0),
        id="shared_daily_market_intelligence",
    )
    scheduler.add_job(
        tasks.generate_personalized_daily_reports,
        CronTrigger(hour=0, minute=10),
        id="personalized_daily_reports",
    )
    scheduler.add_job(
        tasks.scan_market_anomalies,
        IntervalTrigger(minutes=15),
        id="market_anomaly_scan",
    )
    scheduler.add_job(
        tasks.scan_market_anomalies, IntervalTrigger(hours=1), id="funding_oi_scan"
    )
    scheduler.add_job(
        tasks.generate_shared_daily_market_intelligence,
        IntervalTrigger(hours=4),
        id="market_regime_summary",
    )
    scheduler.add_job(
        tasks.dispatch_due_daily_briefs,
        IntervalTrigger(minutes=1),
        id="dispatch_due_daily_briefs",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        tasks.retry_notification_deliveries,
        IntervalTrigger(minutes=1),
        id="retry_notification_deliveries",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        tasks.check_subscription_status,
        CronTrigger(hour=1, minute=0),
        id="subscription_status_check",
    )
    scheduler.add_job(
        tasks.refresh_earnings_gamma_candidates,
        IntervalTrigger(hours=48),
        id="earnings_gamma_refresh",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        tasks.sync_portfolio_autopilot_accounts,
        IntervalTrigger(minutes=15),
        id="portfolio_autopilot_account_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        tasks.sync_nautilus_runtime_runs,
        IntervalTrigger(seconds=settings.nautilus_runtime_sync_interval_seconds),
        id="nautilus_runtime_run_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        tasks.sync_nautilus_paper_accounts,
        IntervalTrigger(seconds=settings.nautilus_runtime_sync_interval_seconds),
        id="nautilus_paper_account_sync",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        tasks.reconcile_active_trading_accounts,
        IntervalTrigger(minutes=settings.nautilus_reconcile_interval_minutes),
        id="nautilus_account_reconciliation",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        tasks.refresh_nautilus_public_market_data,
        IntervalTrigger(seconds=settings.nautilus_market_refresh_interval_seconds),
        id="nautilus_public_market_refresh",
        max_instances=1,
        coalesce=True,
    )
    if settings.data_sync_worker_enabled:
        scheduler.add_job(
            tasks.sync_data_provider,
            IntervalTrigger(minutes=settings.rss_sync_interval),
            args=["rss"],
            id="provider_rss_sync",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            tasks.sync_data_provider,
            IntervalTrigger(minutes=settings.fintwit_sync_interval),
            args=["fintwit"],
            id="provider_fintwit_sync",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            tasks.sync_data_provider,
            IntervalTrigger(minutes=settings.x_sync_interval),
            args=["x-twitter"],
            id="provider_x_sync",
            max_instances=1,
            coalesce=True,
        )
        if settings.bloomberg_mode in {"mock", "production"}:
            scheduler.add_job(
                tasks.sync_data_provider,
                IntervalTrigger(hours=1),
                args=["bloomberg"],
                id="provider_bloomberg_sync",
                max_instances=1,
                coalesce=True,
            )
        scheduler.add_job(
            tasks.purge_expired_source_documents,
            CronTrigger(hour=2, minute=30),
            id="provider_retention_cleanup",
            max_instances=1,
            coalesce=True,
        )
    return scheduler


def main() -> None:
    build_scheduler().start()


if __name__ == "__main__":
    main()
