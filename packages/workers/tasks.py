from __future__ import annotations

import logging
from datetime import timedelta

from apps.api.services.market_intelligence_service import (
    generate_shared_market_intelligence,
)
from apps.api.services.notification_service import send_notification
from apps.api.services.report_service import create_daily_report
from apps.api.services.signal_service import scan_signals
from apps.api.services.runtime_sync_service import sync_runtime_account
from apps.api.services.portfolio_service import run_autopilot_review, sync_account
from apps.api.services.data_source_service import sync_all_providers, sync_provider
from apps.api.services.daily_push_service import next_delivery, render_daily_brief_delivery
from apps.api.services.entitlement_service import get_user_entitlement
from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from apps.api.services.skill_service import begin_module_skill_invocation, finish_module_skill_invocation
from apps.api.config import get_settings
from packages.database.models import (
    AccountSnapshot,
    DailyBriefPreference,
    PortfolioAutopilotReview,
    RawDocument,
    ReconciliationRecord,
    StrategyRun,
    TradingAccount,
    User,
    UserPreference,
    NotificationDelivery,
    utcnow,
)
from packages.database.session import SessionLocal
from packages.billing.budgets import AutomationBudgetExceeded, pause_automation_budget
from packages.trading.runtime_client import NautilusRuntimeClient
from packages.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


def _persist_budget_pause(db, user_id: str, automation_key: str, exc: Exception) -> None:
    db.rollback()
    pause_automation_budget(db, user_id, automation_key, str(exc))
    db.commit()


@celery_app.task(name="puregamma.recover_stale_credit_reservations")
def recover_stale_credit_reservations() -> dict:
    from apps.api.services.credit_service import recover_stale_reservations

    db = SessionLocal()
    try:
        return {"refunded": recover_stale_reservations(db)}
    finally:
        db.close()


@celery_app.task(name="puregamma.retry_notification_deliveries")
def retry_notification_deliveries() -> dict:
    db = SessionLocal()
    retried = sent = failed = 0
    try:
        query = db.query(NotificationDelivery).filter(NotificationDelivery.status == "failed_retryable", NotificationDelivery.next_retry_at <= utcnow()).order_by(NotificationDelivery.next_retry_at).limit(100)
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        rows = query.all()
        for row in rows:
            try:
                retried += 1
                payload = row.payload or {}
                result = send_notification(
                    db,
                    row.user_id,
                    row.channel,
                    str(payload.get("message", "")),
                    {
                        "idempotency_key": row.idempotency_key,
                        "locale": row.locale,
                        **({"automation_key": payload["automation_key"]} if payload.get("automation_key") else {}),
                        **({"report_id": payload["report_id"]} if payload.get("report_id") else {}),
                    },
                )
                if result.status == "sent":
                    sent += 1
                elif result.status == "failed_permanent":
                    failed += 1
            except AutomationBudgetExceeded as exc:
                automation_key = str((row.payload or {}).get("automation_key") or "notification_delivery")
                _persist_budget_pause(db, row.user_id, automation_key, exc)
                failed += 1
                logger.warning("notification_retry_budget_paused user_id=%s", row.user_id)
            except Exception:
                db.rollback()
                failed += 1
                logger.exception("notification_retry_failed delivery_id=%s", row.id)
        return {"retried": retried, "sent": sent, "failed": failed}
    finally:
        db.close()


def _default_brief_timezone(locale: str) -> str:
    return "Asia/Shanghai" if locale == "zh" else "UTC"


def ensure_daily_brief_defaults(db) -> int:
    """Auto-provision an enabled email daily brief for users who never configured one.

    Keeps the daily brief on autopilot: every account gets a scheduled morning
    brief unless it explicitly disables or customizes the preference.
    """
    missing = (
        db.query(User)
        .outerjoin(DailyBriefPreference, DailyBriefPreference.user_id == User.id)
        .filter(DailyBriefPreference.user_id.is_(None))
        .limit(200)
        .all()
    )
    created = 0
    for user in missing:
        locale = user.preference.locale if user.preference else "en"
        timezone_name = _default_brief_timezone(locale)
        local_time = "08:30"
        recipient = (user.preference.email_recipient if user.preference else None) or user.email
        db.add(
            DailyBriefPreference(
                user_id=user.id,
                enabled=True,
                channel="email",
                locale=locale,
                timezone=timezone_name,
                local_time=local_time,
                recipient=recipient,
                next_delivery_at=next_delivery(timezone_name, local_time),
            )
        )
        created += 1
    if created:
        db.commit()
    return created


@celery_app.task(name="puregamma.dispatch_due_daily_briefs")
def dispatch_due_daily_briefs() -> dict:
    db = SessionLocal()
    sent = skipped = failed = 0
    try:
        provisioned = ensure_daily_brief_defaults(db)
        query = db.query(DailyBriefPreference).filter(DailyBriefPreference.enabled.is_(True), DailyBriefPreference.next_delivery_at <= utcnow()).order_by(DailyBriefPreference.next_delivery_at).limit(100)
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        rows = query.all()
        for preference in rows:
            user = db.get(User, preference.user_id)
            scheduled_for = preference.next_delivery_at
            try:
                entitlement = get_user_entitlement(db, user.id)
                if preference.channel not in entitlement["notification_channels"]:
                    preference.enabled = False
                    preference.next_delivery_at = None
                    db.commit()
                    skipped += 1
                    continue
                report = create_daily_report(db, user.id, preference.locale, automation_key="daily_brief")
                message = render_daily_brief_delivery(db, preference, report)
                delivery = send_notification(db, user.id, preference.channel, message, {"idempotency_key": f"daily-brief:{user.id}:{preference.channel}:{scheduled_for.isoformat()}", "locale": preference.locale, "report_id": report.id, "automation_key": "daily_brief_delivery"})
                if delivery.status == "sent":
                    sent += 1
                else:
                    skipped += 1
                preference.next_delivery_at = next_delivery(preference.timezone, preference.local_time, utcnow() + timedelta(minutes=1))
                db.commit()
            except AutomationBudgetExceeded as exc:
                user_id = preference.user_id
                _persist_budget_pause(db, user_id, "daily_brief", exc)
                row = db.get(DailyBriefPreference, user_id)
                if row:
                    row.enabled = False
                    row.next_delivery_at = None
                    db.commit()
                skipped += 1
                logger.warning("due_daily_brief_budget_paused user_id=%s", user_id)
            except Exception:
                db.rollback()
                failed += 1
                logger.exception("due_daily_brief_failed user_id=%s", preference.user_id)
        return {"due": len(rows), "sent": sent, "skipped": skipped, "failed": failed, "provisioned": provisioned}
    finally:
        db.close()


@celery_app.task(name="puregamma.refresh_backtest_lab_candles")
def refresh_backtest_lab_candles() -> dict:
    """Daily incremental refresh of the shared BTC/ETH 1d backtest dataset."""
    from packages.backtest.daily_data import refresh_daily_candles

    db = SessionLocal()
    try:
        return refresh_daily_candles(db)
    except Exception:
        logger.exception("backtest_lab_candles_refresh_failed")
        return {"error": "refresh_failed"}
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_portfolio_autopilot_accounts")
def sync_portfolio_autopilot_accounts() -> dict:
    db = SessionLocal()
    synced = 0
    errors = 0
    try:
        preferences = db.query(UserPreference).all()
        for preference in preferences:
            config = preference.portfolio_autopilot_json or {}
            if not config.get("enabled") or not config.get("auto_sync", True):
                continue
            user = db.get(User, preference.user_id)
            accounts = db.query(TradingAccount).filter_by(user_id=preference.user_id, account_type="READ_ONLY", status="ACTIVE").all()
            for account in accounts:
                try:
                    sync_account(db, user, account)
                    synced += 1
                except Exception:
                    db.rollback()
                    logger.exception("portfolio_autopilot_account_sync_failed user_id=%s account_id=%s", preference.user_id, account.id)
                    errors += 1
            cadence = config.get("cadence", "daily")
            last_review = db.query(PortfolioAutopilotReview).filter_by(user_id=preference.user_id).order_by(PortfolioAutopilotReview.created_at.desc()).first()
            interval = timedelta(days=7 if cadence == "weekly" else 1)
            if accounts and (not last_review or utcnow() - last_review.created_at >= interval):
                reservation = None
                skill_invocation_id = None
                try:
                    quote = quote_task(task_type="portfolio_monitor", async_execution=True)
                    date_key = utcnow().date().isoformat()
                    skill_invocation_id, _ = begin_module_skill_invocation(
                        db,
                        user,
                        config.get("skill_refs", []),
                        trigger_source="scheduled_job",
                        input_payload={"query": "Run scheduled portfolio Autopilot review", "portfolio_user_id": user.id, "cadence": cadence},
                        estimated_credits=quote.credits,
                        allow_autopilot=True,
                        required_tool="get_account_snapshot",
                        invocation_id=f"portfolio-scheduled-skill:{user.id}:{date_key}",
                    )
                    db.commit()
                    reservation = reserve_task(
                        db,
                        user.id,
                        quote,
                        f"portfolio-monitor:{user.id}:{date_key}",
                        {"automation_key": "portfolio_monitor", "cadence": cadence},
                    )
                    db.commit()
                    review = run_autopilot_review(db, user)
                    delivery = config.get("delivery", "in_app")
                    if delivery in {"telegram", "imessage"}:
                        findings = "; ".join(item["title"] for item in review["findings"][:5])
                        send_notification(db, user.id, delivery, f"PureGamma AI Portfolio Autopilot\n\n{findings}\n\nUsers bear all risks of using this service. The service provider is not responsible for any AI-generated content.", {"type": "portfolio_autopilot", "reviewed_at": review["last_review"], "automation_key": "portfolio_monitor_delivery"})
                    settle_task(db, user.id, reservation, quote.credits, metadata={"reviewed_at": review["last_review"]})
                    finish_module_skill_invocation(db, skill_invocation_id, status="completed", credits_used=quote.credits, output_summary="Scheduled portfolio Autopilot review", evidence={"reviewed_at": review["last_review"], "account_count": review["account_count"]})
                    db.commit()
                except AutomationBudgetExceeded as exc:
                    if skill_invocation_id:
                        finish_module_skill_invocation(db, skill_invocation_id, status="failed", credits_used=0, error_code="AUTOMATION_BUDGET_EXCEEDED")
                        db.commit()
                    _persist_budget_pause(db, user.id, "portfolio_monitor", exc)
                    current = db.get(UserPreference, preference.user_id)
                    if current:
                        paused_config = dict(current.portfolio_autopilot_json or {})
                        paused_config["enabled"] = False
                        paused_config["pause_reason"] = str(exc)
                        current.portfolio_autopilot_json = paused_config
                        db.commit()
                    logger.warning("portfolio_autopilot_budget_paused user_id=%s", preference.user_id)
                except Exception:
                    db.rollback()
                    if reservation:
                        refund_task(db, user.id, reservation, "PORTFOLIO_MONITOR_FAILED")
                    if skill_invocation_id:
                        finish_module_skill_invocation(db, skill_invocation_id, status="failed", credits_used=0, error_code="PORTFOLIO_MONITOR_FAILED")
                    db.commit()
                    logger.exception("portfolio_autopilot_review_failed user_id=%s", preference.user_id)
                    errors += 1
        return {"synced": synced, "errors": errors}
    finally:
        db.close()


@celery_app.task(name="puregamma.generate_shared_daily_market_intelligence")
def generate_shared_daily_market_intelligence() -> str:
    db = SessionLocal()
    try:
        item = generate_shared_market_intelligence(db)
        return item.id
    finally:
        db.close()


@celery_app.task(name="puregamma.generate_personalized_daily_reports")
def generate_personalized_daily_reports() -> list[str]:
    db = SessionLocal()
    ids = []
    try:
        users = db.query(User).all()
        for user in users:
            try:
                language = (
                    getattr(user.preference, "locale", "en")
                    if user.preference
                    else "en"
                )
                ids.append(create_daily_report(db, user.id, language, automation_key="daily_report").id)
            except AutomationBudgetExceeded as exc:
                _persist_budget_pause(db, user.id, "daily_report", exc)
                logger.warning("daily_report_budget_paused user_id=%s", user.id)
            except Exception:
                db.rollback()
                logger.exception("daily_report_generation_failed user_id=%s", user.id)
        return ids
    finally:
        db.close()


@celery_app.task(name="puregamma.scan_market_anomalies")
def scan_market_anomalies() -> int:
    db = SessionLocal()
    try:
        return len(scan_signals(db))
    finally:
        db.close()


@celery_app.task(name="puregamma.send_daily_reports_to_channels")
def send_daily_reports_to_channels() -> int:
    db = SessionLocal()
    sent = 0
    try:
        from apps.api.services.report_service import create_daily_report
        users = db.query(User).all()
        for user in users:
            pref = user.preference
            if not pref:
                continue
            language = getattr(pref, "locale", "en")
            try:
                report = create_daily_report(db, user.id, language, automation_key="daily_report_delivery")
                db.commit()
            except AutomationBudgetExceeded as exc:
                _persist_budget_pause(db, user.id, "daily_report_delivery", exc)
                logger.warning("daily_delivery_budget_paused user_id=%s", user.id)
                continue
            except Exception:
                db.rollback()
                logger.exception("daily_delivery_report_generation_failed user_id=%s", user.id)
                try:
                    report = create_daily_report(db, user.id, language, automation_key="daily_report_delivery")
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("daily_delivery_report_retry_failed user_id=%s", user.id)
                    continue
            brief_text = report.content_markdown
            if not brief_text:
                brief_text = (
                    "PureGamma 每日简报已生成。Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."
                    if language == "zh"
                    else "PureGamma daily brief is ready. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."
                )
            for channel in pref.notification_channels:
                try:
                    delivery = send_notification(
                        db,
                        user.id,
                        channel,
                        brief_text,
                        {
                            "idempotency_key": f"daily-{user.id}-{channel}-{language}-{utcnow().date().isoformat()}",
                            "locale": language,
                            "report_id": report.id,
                            "automation_key": "daily_report_delivery",
                        },
                    )
                    sent += 1 if delivery.status == "sent" else 0
                except Exception:
                    db.rollback()
                    logger.exception("daily_notification_failed user_id=%s channel=%s", user.id, channel)
        return sent
    finally:
        db.close()


@celery_app.task(name="puregamma.send_unified_daily_brief_to_all")
def send_unified_daily_brief_to_all() -> dict:
    """Render ONE unified brief per locale and broadcast it to every user (free).

    Template-rendered (non-LLM) so all users share the same daily view.
    Free of charge; failures land in the existing NotificationDelivery retry lane.
    """
    from packages.reports.unified_daily_brief import generate_unified_daily_brief

    db = SessionLocal()
    sent = skipped = failed = 0
    try:
        briefs = {
            "en": generate_unified_daily_brief(db, "en"),
            "zh": generate_unified_daily_brief(db, "zh"),
        }
        today = utcnow().date().isoformat()
        users = db.query(User).all()
        for user in users:
            raw_locale = user.preference.locale if user.preference else "en"
            locale = "zh" if raw_locale == "zh" else "en"
            brief_pref = db.get(DailyBriefPreference, user.id)
            channel = "email"
            if brief_pref and brief_pref.enabled and brief_pref.channel in {"email", "imessage"}:
                channel = brief_pref.channel
            if channel == "imessage" and not (brief_pref and brief_pref.recipient and brief_pref.recipient_verified_at):
                channel = "email"
            try:
                delivery = send_notification(
                    db,
                    user.id,
                    channel,
                    briefs[locale],
                    {
                        "idempotency_key": f"unified-brief:{today}:{user.id}:{channel}",
                        "locale": locale,
                        "automation_key": "unified_daily_brief",
                    },
                )
                if delivery.status == "sent":
                    sent += 1
                else:
                    skipped += 1
            except Exception:
                db.rollback()
                failed += 1
                logger.exception("unified_brief_delivery_failed user_id=%s", user.id)
        return {"sent": sent, "skipped": skipped, "failed": failed, "users": len(users)}
    finally:
        db.close()


@celery_app.task(name="puregamma.refresh_earnings_gamma_candidates")
def refresh_earnings_gamma_candidates() -> dict:
    db = SessionLocal()
    try:
        from packages.options.earnings_gamma import (
            force_refresh_earnings,
            is_us_equity_trading_day,
        )

        if not is_us_equity_trading_day():
            return {"skipped": True, "reason": "us_market_closed"}
        candidates = force_refresh_earnings(db, "en")
        return {
            "skipped": False,
            "en_count": len(candidates),
            "zh_count": len(candidates),
        }
    finally:
        db.close()


@celery_app.task(name="puregamma.check_subscription_status")
def check_subscription_status() -> dict:
    from apps.api.services.billing_service import reconcile_stripe_subscriptions

    db = SessionLocal()
    try:
        return reconcile_stripe_subscriptions(db)
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_data_provider")
def sync_data_provider(provider_id: str) -> dict:
    db = SessionLocal()
    try:
        run = sync_provider(db, provider_id)
        return {"id": run.id, "provider": provider_id, "status": run.status}
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_all_data_providers")
def sync_all_data_providers() -> list[dict]:
    db = SessionLocal()
    try:
        return [
            {"id": row.id, "provider": row.provider_id, "status": row.status}
            for row in sync_all_providers(db)
        ]
    finally:
        db.close()


@celery_app.task(name="puregamma.purge_expired_source_documents")
def purge_expired_source_documents() -> int:
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(days=get_settings().data_retention_days)
        rows = db.query(RawDocument).filter(RawDocument.fetched_at < cutoff).all()
        count = len(rows)
        for row in rows:
            db.delete(row)
        db.commit()
        return count
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_nautilus_runtime_runs")
def sync_nautilus_runtime_runs() -> dict:
    db = SessionLocal()
    updated = 0
    errors = 0
    client = NautilusRuntimeClient()
    try:
        rows = (
            db.query(StrategyRun)
            .filter(
                StrategyRun.status.in_(
                    ["PENDING", "RUNNING", "PAUSED", "RECONCILIATION_REQUIRED"]
                ),
            )
            .all()
        )
        for row in rows:
            try:
                runtime = client.run(row.runtime_run_id).get("run", {})
                row.status = runtime.get("status", row.status)
                row.performance_json = runtime.get("performance", row.performance_json)
                row.error_code = None
                row.error_message = None
                updated += 1
            except Exception as exc:
                row.error_code = "RUNTIME_SYNC_FAILED"
                row.error_message = str(exc)[:300]
                errors += 1
        db.commit()
        return {"updated": updated, "errors": errors}
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_nautilus_paper_accounts")
def sync_nautilus_paper_accounts() -> dict:
    db = SessionLocal()
    synced = 0
    errors = 0
    client = NautilusRuntimeClient()
    try:
        accounts = db.query(TradingAccount).filter_by(status="ACTIVE").all()
        for account in accounts:
            try:
                sync_runtime_account(db, account, runtime=client)
                synced += 1
            except Exception:
                db.rollback()
                errors += 1
        return {"synced": synced, "errors": errors}
    finally:
        db.close()


@celery_app.task(name="puregamma.reconcile_active_trading_accounts")
def reconcile_active_trading_accounts() -> dict:
    """Operational safety reconciliation is never blocked by user credits."""
    db = SessionLocal()
    reconciled = 0
    errors = 0
    client = NautilusRuntimeClient()
    try:
        accounts = db.query(TradingAccount).filter_by(status="ACTIVE").all()
        for account in accounts:
            try:
                bucket = int(utcnow().timestamp() // 300)
                ack = client.command(
                    "reconcile",
                    f"worker:reconcile:{account.id}:{bucket}",
                    {"account_id": account.id},
                )
                exchange = ack.get("exchange", {})
                db.add(
                    ReconciliationRecord(
                        user_id=account.user_id,
                        account_id=account.id,
                        status=ack.get("status", "ERROR"),
                        local_state_json={"orders": ack.get("local_open_orders", [])},
                        exchange_state_json=exchange,
                        differences_json=ack.get("unknown_orders", []),
                        actions_json=["pause_opening"]
                        if ack.get("opening_paused")
                        else [],
                        raw_event_reference={
                            "runtime_command_id": ack.get("command_id"),
                            "source": "scheduler",
                        },
                        completed_at=utcnow(),
                    )
                )
                snapshot = exchange.get("account")
                if snapshot:
                    db.add(
                        AccountSnapshot(
                            user_id=account.user_id,
                            account_id=account.id,
                            balance=snapshot["balance"],
                            equity=snapshot["equity"],
                            available_margin=snapshot["available_margin"],
                            daily_pnl=snapshot["daily_pnl"],
                            drawdown=snapshot["drawdown"],
                            exposure=snapshot["exposure"],
                            stale=snapshot["stale"],
                            raw_event_reference={
                                "runtime_command_id": ack.get("command_id"),
                                "source": "scheduler",
                            },
                        )
                    )
                reconciled += 1
            except Exception as exc:
                db.add(
                    ReconciliationRecord(
                        user_id=account.user_id,
                        account_id=account.id,
                        status="ERROR",
                        error_code="RUNTIME_UNAVAILABLE",
                        error_message=str(exc)[:300],
                        completed_at=utcnow(),
                    )
                )
                errors += 1
            db.commit()
        return {"reconciled": reconciled, "errors": errors}
    finally:
        db.close()


@celery_app.task(name="puregamma.refresh_nautilus_public_market_data")
def refresh_nautilus_public_market_data() -> dict:
    interval = max(5, get_settings().nautilus_market_refresh_interval_seconds)
    bucket = int(utcnow().timestamp() // interval)
    return NautilusRuntimeClient().command(
        "refresh_market_data",
        f"worker:market-refresh:{bucket}",
        {"symbols": []},
    )
