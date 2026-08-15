from __future__ import annotations

import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.api.services.market_intelligence_service import (
    generate_shared_market_intelligence,
    latest_or_create_intelligence,
)
from apps.api.services.notification_service import send_notification
from apps.api.services.report_service import create_daily_report, create_typed_daily_report
from apps.api.services.cost_control_service import DailyLimitExceededError
from apps.api.services.signal_service import scan_signals
from apps.api.services.runtime_sync_service import sync_runtime_account
from apps.api.services.portfolio_service import PlaidDataPending, _snapshot_is_stale, sync_account
from apps.api.services.data_source_service import sync_all_providers, sync_provider
from apps.api.services.daily_push_service import next_delivery
from apps.api.services.entitlement_service import get_user_entitlement
from apps.api.services.credit_service import quote_task, refund_task, reserve_task, settle_task
from apps.api.services.skill_service import finish_module_skill_invocation
from apps.api.services.skill_workflow_service import invoke_workflow_skill
from apps.api.config import get_settings
from packages.database.models import (
    AccountSnapshot,
    BacktestRun,
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
from packages.reports.templates import disclaimer_for
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


@celery_app.task(name="puregamma.sync_gateway_provider_metadata")
def sync_gateway_provider_metadata() -> dict:
    """Daily official catalog refresh; new price snapshots remain pending review."""
    from packages.gateway.metadata import sync_all_provider_metadata

    if not get_settings().gateway_enabled:
        return {"status": "disabled"}

    db = SessionLocal()
    try:
        rows = sync_all_provider_metadata(db, triggered_by="scheduler")
        return {"synced": len(rows), "pending_review": sum(row.status == "pending_review" for row in rows)}
    except Exception:
        logger.exception("gateway_provider_metadata_sync_failed")
        raise
    finally:
        db.close()


@celery_app.task(name="puregamma.healthcheck_gateway_providers")
def healthcheck_gateway_providers() -> dict:
    from packages.gateway.metadata import health_check_providers

    if not get_settings().gateway_enabled:
        return {"status": "disabled"}

    db = SessionLocal()
    try:
        return {"providers": health_check_providers(db)}
    except Exception:
        logger.exception("gateway_provider_healthcheck_failed")
        raise
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


# ---------------------------------------------------------------------------
# Unified daily report orchestrator (P0-8)
#
# SINGLE-ORCHESTRATOR INVARIANT: ``_orchestrate_due_daily_briefs`` is the ONLY
# per-user daily dispatch path. The legacy chains
# (send_unified_daily_brief_to_all / generate_personalized_daily_reports /
# send_daily_reports_to_channels) are thin wrappers that warm shared
# intelligence and delegate here, so shared intelligence is built once and
# per-user reports/deliveries are idempotent under exactly one code path.
#
# Flow: shared intelligence once → per-user personalization → report cache →
# multi-channel dispatch.
# ---------------------------------------------------------------------------

DEFAULT_DAILY_REPORT_TYPES = ["crypto_daily", "us_daily", "week_ahead_events", "portfolio_daily"]

# Generic-failure backoff in minutes: 2**failure_count capped at 240 (1, 2, 4,
# ... capped) — a failing preference is NEVER left due-again immediately.
MAX_FAILURE_BACKOFF_MINUTES = 240


def _local_date_for(preference: DailyBriefPreference) -> date:
    try:
        zone = ZoneInfo(preference.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return utcnow().astimezone(zone).date()


def _delivery_message(preference: DailyBriefPreference, report) -> str:
    disclaimer = disclaimer_for(preference.locale)
    body = (report.content_markdown or "").rstrip()
    if disclaimer not in body:
        body = f"{body}\n\n{disclaimer}" if body else disclaimer
    if len(body) <= preference.max_length:
        return body
    available = max(0, preference.max_length - len(disclaimer) - 2)
    return f"{(report.content_markdown or '')[:available].rstrip()}\n\n{disclaimer}"


def _already_delivered(db, user_id: str, channel: str, report_id: str) -> bool:
    """Exactly-once guard across backoff retries: a retry gets a new
    scheduled_for-based idempotency key, so also dedupe on the delivered report."""
    existing = (
        db.query(NotificationDelivery.id)
        .filter(
            NotificationDelivery.user_id == user_id,
            NotificationDelivery.channel == channel,
            NotificationDelivery.status == "sent",
            NotificationDelivery.payload["report_id"].as_string() == report_id,
        )
        .first()
    )
    return existing is not None


def _combined_email_message(preference: DailyBriefPreference, reports: list) -> str:
    """Consolidate all due report types into a single email body.

    Each report keeps its own max_length truncation (same content volume as
    before), then the parts are joined into one mail so users get a single
    consolidated brief instead of one mail per report type.
    """
    parts = []
    for _report_type, report in reports:
        message = _delivery_message(preference, report)
        if message.strip():
            parts.append(message)
    if not parts:
        return ""
    return "\n\n---\n\n".join(parts)


def _process_due_preference(db, user: User, preference: DailyBriefPreference, scheduled_for) -> dict:
    """Generate cached typed reports for one due preference and dispatch them.

    Raises on report-generation failures (the caller classifies them); channel
    delivery problems are contained per channel so one bad channel never blocks
    the rest of the user's dispatch.
    """
    entitlement = get_user_entitlement(db, user.id)
    entitled_channels = set(entitlement["notification_channels"])
    configured = [str(channel).lower() for channel in (preference.channels or [preference.channel]) if channel]
    channels = [channel for channel in dict.fromkeys(configured) if channel in entitled_channels]
    report_types = list(preference.report_types or DEFAULT_DAILY_REPORT_TYPES)
    local_date = _local_date_for(preference)

    reports = []
    for report_type in report_types:
        report = create_typed_daily_report(
            db,
            user.id,
            report_type,
            preference.locale,
            local_date=local_date,
            scheduled=True,
            automation_key="daily_brief",
        )
        reports.append((report_type, report))

    sent = skipped = 0
    email_bundle: list = []
    for report_type, report in reports:
        message = _delivery_message(preference, report)
        for channel in [*channels, "web"]:
            if channel == "email":
                # Merge all due report types into ONE email (consolidated brief).
                email_bundle.append((report_type, report))
                continue
            if _already_delivered(db, user.id, channel, report.id):
                skipped += 1
                continue
            try:
                delivery = send_notification(
                    db,
                    user.id,
                    channel,
                    message,
                    {
                        "idempotency_key": f"daily-brief:{user.id}:{channel}:{report_type}:{scheduled_for.isoformat()}",
                        "locale": preference.locale,
                        "report_id": report.id,
                        "automation_key": "daily_brief_delivery",
                    },
                )
            except Exception:
                db.rollback()
                skipped += 1
                logger.exception("daily_brief_channel_dispatch_failed user_id=%s channel=%s report_type=%s", user.id, channel, report_type)
                continue
            if delivery.status == "sent":
                sent += 1
            else:
                skipped += 1
    if email_bundle:
        email_message = _combined_email_message(preference, email_bundle)
        email_report_ids = [report.id for _report_type, report in email_bundle]
        try:
            delivery = send_notification(
                db,
                user.id,
                "email",
                email_message,
                {
                    "idempotency_key": f"daily-brief:{user.id}:email:combined:{scheduled_for.isoformat()}",
                    "locale": preference.locale,
                    "report_ids": email_report_ids,
                    "automation_key": "daily_brief_delivery",
                },
            )
        except Exception:
            db.rollback()
            skipped += 1
            logger.exception("daily_brief_email_merge_failed user_id=%s", user.id)
        else:
            if delivery.status == "sent":
                sent += 1
            else:
                skipped += 1
    return {"sent": sent, "skipped": skipped}


def _orchestrate_due_daily_briefs(db) -> dict:
    provisioned = ensure_daily_brief_defaults(db)
    # Shared intelligence is built at most once and reused by every per-user
    # renderer below (no duplicated LLM calls across users).
    try:
        latest_or_create_intelligence(db)
    except Exception:
        db.rollback()
        logger.exception("daily_orchestrator_intelligence_warm_failed")
    query = db.query(DailyBriefPreference).filter(DailyBriefPreference.enabled.is_(True), DailyBriefPreference.next_delivery_at <= utcnow()).order_by(DailyBriefPreference.next_delivery_at).limit(100)
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    rows = query.all()
    sent = skipped = failed = 0
    for preference in rows:
        user = db.get(User, preference.user_id)
        scheduled_for = preference.next_delivery_at
        if not user:
            failed += 1
            continue
        try:
            outcome = _process_due_preference(db, user, preference, scheduled_for)
            preference.failure_count = 0
            preference.last_error = None
            preference.next_delivery_at = next_delivery(preference.timezone, preference.local_time, utcnow() + timedelta(minutes=1))
            db.commit()
            sent += outcome["sent"]
            skipped += outcome["skipped"]
            logger.info("daily_brief_dispatched user_id=%s sent=%s skipped=%s", user.id, outcome["sent"], outcome["skipped"])
        except DailyLimitExceededError:
            # THE incident fix: a daily-limit rejection is terminal for TODAY —
            # advance to the next scheduled local slot instead of leaving the
            # preference due every minute forever.
            db.rollback()
            row = db.get(DailyBriefPreference, preference.user_id)
            if row:
                row.failure_count = 0
                row.last_error = "DAILY_LIMIT"
                row.next_delivery_at = next_delivery(row.timezone, row.local_time, utcnow() + timedelta(minutes=1))
                db.commit()
            skipped += 1
            logger.info("daily_brief_daily_limit_terminal user_id=%s", preference.user_id)
        except AutomationBudgetExceeded as exc:
            user_id = preference.user_id
            _persist_budget_pause(db, user_id, "daily_brief", exc)
            row = db.get(DailyBriefPreference, user_id)
            if row:
                row.enabled = False
                row.next_delivery_at = None
                row.last_error = "AutomationBudgetExceeded"
                db.commit()
            skipped += 1
            logger.warning("due_daily_brief_budget_paused user_id=%s", user_id)
        except Exception as exc:
            # Generic failure: exponential backoff (2**failure_count minutes,
            # capped) — next_delivery_at ALWAYS advances, never re-due in 1 min.
            db.rollback()
            row = db.get(DailyBriefPreference, preference.user_id)
            if row:
                failure_count = (row.failure_count or 0) + 1
                row.failure_count = failure_count
                row.last_error = type(exc).__name__
                backoff_minutes = min(2 ** failure_count, MAX_FAILURE_BACKOFF_MINUTES)
                row.next_delivery_at = utcnow() + timedelta(minutes=backoff_minutes)
                db.commit()
            failed += 1
            logger.exception("due_daily_brief_failed user_id=%s", preference.user_id)
    return {"due": len(rows), "sent": sent, "skipped": skipped, "failed": failed, "provisioned": provisioned}


@celery_app.task(name="puregamma.dispatch_due_daily_briefs")
def dispatch_due_daily_briefs() -> dict:
    from packages.workers.redis_lock import acquire_redis_lock, release_redis_lock

    if not acquire_redis_lock("dispatch_due_daily_briefs", ttl_seconds=900):
        logger.warning("daily_brief_dispatch_skipped_lock_held")
        return {"status": "skipped_lock_held"}
    db = SessionLocal()
    try:
        return _orchestrate_due_daily_briefs(db)
    except Exception:
        logger.exception("daily_brief_dispatch_failed")
        from apps.api.services.ops_alert import notify_ops

        notify_ops("Daily brief dispatch failed; users may not have received their digest", level="error")
        return {"error": "dispatch_failed"}
    finally:
        release_redis_lock("dispatch_due_daily_briefs")
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


@celery_app.task(name="puregamma.execute_unified_backtest", bind=True, max_retries=0)
def execute_unified_backtest(self, run_id: str) -> dict:
    """Execute one paid research backtest outside the API request process."""
    from apps.api.services.unified_backtest_service import execute_unified_run, serialize_unified_run

    db = SessionLocal()
    try:
        row = execute_unified_run(db, run_id)
        invocation_id = ((row.spec_json or {}).get("context_meta") or {}).get("skill_invocation_id")
        if invocation_id:
            finish_module_skill_invocation(db, invocation_id, status="completed", credits_used=row.credits_spent, output_summary=f"{row.strategy_name} / {row.asset}", evidence={"backtest_id": row.id, "source": row.engine})
            db.commit()
        return serialize_unified_run(row)
    except Exception as exc:
        logger.exception("unified_backtest_failed run_id=%s", run_id)
        row = db.get(BacktestRun, run_id)
        invocation_id = ((row.spec_json or {}).get("context_meta") or {}).get("skill_invocation_id") if row else None
        if invocation_id:
            finish_module_skill_invocation(db, invocation_id, status="failed", credits_used=0, error_code="BACKTEST_EXECUTION_FAILED")
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(name="puregamma.execute_research_run", bind=True, max_retries=0)
def execute_research_run(self, run_id: str) -> dict:
    """Execute one isolated research run in an ephemeral Docker container."""
    from apps.api.services.research_runner_service import (
        execute_research_run as _execute_research_run,
        serialize_research_run,
    )

    db = SessionLocal()
    try:
        row = _execute_research_run(db, run_id)
        return serialize_research_run(row)
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_plaid_investments_account", bind=True, max_retries=8)
def sync_plaid_investments_account(self, account_id: str) -> dict:
    """Fetch holdings and investment activity after Link, refresh, or webhook."""
    db = SessionLocal()
    try:
        account = db.get(TradingAccount, account_id)
        if not account or account.venue != "PLAID" or account.status != "ACTIVE":
            return {"account_id": account_id, "status": "ignored"}
        user = db.get(User, account.user_id)
        if not user:
            return {"account_id": account_id, "status": "missing_user"}
        sync_account(db, user, account, include_transactions=True)
        return {"account_id": account_id, "status": "synced"}
    except PlaidDataPending as exc:
        delay = min(600, 30 * (self.request.retries + 1))
        raise self.retry(exc=exc, countdown=delay)
    finally:
        db.close()


def _persist_autopilot_review_from_workflow(db, user, accounts, skill_run) -> dict:
    """Keep the Autopilot review contract (cadence gating + autopilot_view) on
    top of the portfolio_impact_review workflow output — no bespoke rules."""
    output = (((skill_run.evidence_json or {}).get("workflow") or {}).get("output") or {})
    nav = output.get("nav")
    nav_value = float(nav) if isinstance(nav, (int, float)) and not isinstance(nav, bool) else 0.0
    findings: list[dict] = []
    for impact in output.get("impacts") or []:
        title = impact.get("event_title") or impact.get("event_type")
        symbol = impact.get("symbol")
        if title and symbol:
            findings.append({"severity": "info", "title": f"{symbol}: {title}"})
    for gap in output.get("gaps") or []:
        findings.append({"severity": "warning", "title": str(gap)})
    if not findings:
        findings.append({"severity": "info", "title": "No freshness or concentration exception detected"})
    review = PortfolioAutopilotReview(
        user_id=user.id,
        nav=nav_value,
        account_count=len(accounts),
        findings_json=findings,
        concentration_json={},
        status="COMPLETED",
        data_as_of=utcnow(),
    )
    db.add(review)
    db.commit()
    return {"last_review": review.created_at.isoformat(), "findings": findings, "account_count": len(accounts)}


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
                try:
                    quote = quote_task(task_type="portfolio_monitor", async_execution=True)
                    date_key = utcnow().date().isoformat()
                    reservation = reserve_task(
                        db,
                        user.id,
                        quote,
                        f"portfolio-monitor:{user.id}:{date_key}",
                        {"automation_key": "portfolio_monitor", "cadence": cadence},
                    )
                    db.commit()
                    # The scheduled review is the portfolio_impact_review workflow
                    # Skill: one shared invocation path, fully audited on SkillRun.
                    skill_run = invoke_workflow_skill(
                        db,
                        user=user,
                        slug="portfolio_impact_review",
                        inputs={"locale": "en", "cadence": cadence},
                        trigger_source="scheduled_job",
                        allow_autopilot=True,
                        invocation_id=f"portfolio-scheduled-skill:{user.id}:{date_key}",
                    )
                    review = _persist_autopilot_review_from_workflow(db, user, accounts, skill_run)
                    delivery = config.get("delivery", "in_app")
                    if delivery in {"telegram", "imessage"}:
                        findings = "; ".join(item["title"] for item in review["findings"][:5])
                        send_notification(db, user.id, delivery, f"PureGamma AI Portfolio Autopilot\n\n{findings}", {"type": "portfolio_autopilot", "reviewed_at": review["last_review"], "automation_key": "portfolio_monitor_delivery"})
                    settle_task(db, user.id, reservation, quote.credits, metadata={"reviewed_at": review["last_review"]})
                    db.commit()
                except AutomationBudgetExceeded as exc:
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
                    db.commit()
                    logger.exception("portfolio_autopilot_review_failed user_id=%s", preference.user_id)
                    errors += 1
        return {"synced": synced, "errors": errors}
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_all_portfolio_accounts")
def sync_all_portfolio_accounts() -> dict:
    """General scheduled NAV refresh for every connected portfolio account.

    Unlike ``sync_portfolio_autopilot_accounts`` this is not gated on an
    Autopilot configuration, so any connected portfolio keeps a fresh snapshot
    and NAV history even when Autopilot is off. Accounts are processed
    independently: a failing source (Plaid delay, EVM RPC, CEX outage) records
    an error for that account only and never overwrites another account's last
    valid snapshot. Accounts whose latest snapshot is still fresh are skipped.
    """
    db = SessionLocal()
    synced = 0
    skipped = 0
    errors = 0
    accounts_seen = 0
    try:
        accounts = db.query(TradingAccount).filter_by(account_type="READ_ONLY", status="ACTIVE").all()
        user_cache: dict[str, User | None] = {}
        for account in accounts:
            if account.user_id not in user_cache:
                user_cache[account.user_id] = db.get(User, account.user_id)
            user = user_cache[account.user_id]
            if user is None:
                continue
            try:
                if get_user_entitlement(db, user.id).get("portfolio_access") != "standard":
                    continue
            except Exception:
                continue
            accounts_seen += 1
            latest = db.query(AccountSnapshot).filter_by(user_id=user.id, account_id=account.id).order_by(AccountSnapshot.captured_at.desc()).first()
            if latest and not _snapshot_is_stale(account, latest):
                skipped += 1
                continue
            try:
                sync_account(db, user, account)
                synced += 1
            except Exception:
                db.rollback()
                logger.exception("portfolio_nav_sync_failed user_id=%s account_id=%s", user.id, account.id)
                errors += 1
        return {"synced": synced, "skipped": skipped, "errors": errors, "accounts": accounts_seen}
    finally:
        db.close()


@celery_app.task(name="puregamma.generate_portfolio_nav")
def generate_portfolio_nav(snapshot_date=None) -> dict:
    """Write daily per-user portfolio NAV snapshots (estimated, unofficial).

    For every user with an active READ_ONLY portfolio account, NAV = the sum of
    the latest account equity, with a per-symbol breakdown from the latest
    position snapshots. Idempotent per ``(user_id, snapshot_date)``.

    Partial-source safety: accounts that cannot produce a snapshot are skipped
    and marked ``partial``; a user with no usable account data is skipped
    entirely so the previous valid snapshot is preserved.
    """
    from datetime import date as _date

    from packages.database.models import PortfolioNavSnapshot, PositionSnapshot

    db = SessionLocal()
    snapshot_day = snapshot_date or _date.today()
    written = 0
    skipped = 0
    partial_users = 0
    errors = 0
    try:
        accounts = db.query(TradingAccount).filter_by(account_type="READ_ONLY", status="ACTIVE").all()
        by_user: dict[str, list[TradingAccount]] = {}
        for account in accounts:
            if account.user_id not in by_user:
                by_user[account.user_id] = []
            by_user[account.user_id].append(account)

        for user_id, user_accounts in by_user.items():
            try:
                equities = []
                cash = 0.0
                included_accounts = []
                failed_account = False
                positions: dict[str, dict] = {}
                data_as_of = None
                for account in user_accounts:
                    latest = (
                        db.query(AccountSnapshot)
                        .filter_by(user_id=user_id, account_id=account.id)
                        .order_by(AccountSnapshot.captured_at.desc())
                        .first()
                    )
                    if latest is None:
                        failed_account = True
                        continue
                    equities.append(latest.equity if latest.equity is not None else latest.balance)
                    cash += latest.balance if latest.balance is not None else 0.0
                    included_accounts.append(account.id)
                    if data_as_of is None or (latest.captured_at and latest.captured_at > data_as_of):
                        data_as_of = latest.captured_at
                    # PositionSnapshot rows are append-only history: keep only
                    # the LATEST row per symbol (per account), otherwise the
                    # same position is counted once per sync.
                    seen_symbols: set[str] = set()
                    for pos in (
                        db.query(PositionSnapshot)
                        .filter_by(user_id=user_id, account_id=account.id)
                        .order_by(PositionSnapshot.captured_at.desc())
                        .limit(200)
                        .all()
                    ):
                        symbol = pos.instrument
                        if symbol in seen_symbols:
                            continue
                        seen_symbols.add(symbol)
                        quantity = float(pos.quantity or 0)
                        mark_price = float(pos.mark_price or 0)
                        entry = positions.setdefault(
                            symbol,
                            {
                                "quantity": 0.0,
                                "mark_price": mark_price,
                                "value": 0.0,
                                "unrealized_pnl": 0.0,
                            },
                        )
                        entry["quantity"] += quantity
                        entry["value"] += quantity * mark_price
                        entry["unrealized_pnl"] += float(pos.unrealized_pnl or 0.0)
                        entry["mark_price"] = mark_price
                if not included_accounts:
                    # No usable source data: preserve the previous valid snapshot.
                    skipped += 1
                    continue
                total_nav = sum(equities)
                partial = failed_account
                if partial:
                    partial_users += 1
                row = (
                    db.query(PortfolioNavSnapshot)
                    .filter_by(user_id=user_id, snapshot_date=snapshot_day)
                    .first()
                )
                if row is None:
                    row = PortfolioNavSnapshot(user_id=user_id, snapshot_date=snapshot_day)
                    db.add(row)
                row.total_nav = total_nav
                row.cash_balance = cash
                row.account_count = len(included_accounts)
                row.positions_json = positions
                row.source_accounts_json = included_accounts
                row.partial = partial
                row.data_as_of = data_as_of
                db.commit()
                written += 1
            except Exception:
                db.rollback()
                logger.exception("generate_portfolio_nav_failed user_id=%s", user_id)
                errors += 1
        return {
            "written": written,
            "skipped": skipped,
            "partial_users": partial_users,
            "errors": errors,
            "snapshot_date": snapshot_day.isoformat(),
        }
    finally:
        db.close()


@celery_app.task(name="puregamma.generate_shared_daily_market_intelligence")
def generate_shared_daily_market_intelligence() -> str:
    """Warm the shared daily market intelligence record.

    Scheduled at 00:00 UTC and every 4h; the every-minute orchestrator relies
    on the warmed record being present for per-user brief generation.
    """
    db = SessionLocal()
    try:
        item = generate_shared_market_intelligence(db)
        return item.id
    finally:
        db.close()


@celery_app.task(name="puregamma.generate_personalized_daily_reports")
def generate_personalized_daily_reports() -> dict:
    """Thin wrapper (single-orchestrator invariant): warm shared intelligence,
    then delegate ALL per-user work to the unified daily orchestrator."""
    db = SessionLocal()
    try:
        latest_or_create_intelligence(db)
        return _orchestrate_due_daily_briefs(db)
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
def send_daily_reports_to_channels() -> dict:
    """Thin wrapper (single-orchestrator invariant): warm shared intelligence,
    then delegate ALL per-user channel dispatch to the unified orchestrator."""
    db = SessionLocal()
    try:
        latest_or_create_intelligence(db)
        return _orchestrate_due_daily_briefs(db)
    finally:
        db.close()


@celery_app.task(name="puregamma.send_unified_daily_brief_to_all")
def send_unified_daily_brief_to_all() -> dict:
    """Thin wrapper (single-orchestrator invariant): warm shared intelligence,
    then delegate the broadcast to the unified daily orchestrator.

    The one-shared-template broadcast was replaced by the typed per-user
    reports the orchestrator renders and caches; this task name stays
    registered for deploy compatibility only.
    """
    db = SessionLocal()
    try:
        latest_or_create_intelligence(db)
        return _orchestrate_due_daily_briefs(db)
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


@celery_app.task(name="puregamma.refresh_mstr_btc_dashboard")
def refresh_mstr_btc_dashboard() -> dict:
    """Warm the MSTR/BTC opportunity dashboard cache and append series points."""
    from apps.api.services import mstr_btc_service

    pack = mstr_btc_service.refresh_fact_pack()
    usable = bool(pack.get("kpis") or pack.get("mstr") or pack.get("tracker"))
    return {"usable": usable, "errors": list(pack.get("errors") or [])}


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


@celery_app.task(name="puregamma.build_research_events")
def build_research_events() -> dict:
    from apps.api.services import research_event_service

    db = SessionLocal()
    try:
        snapshot = research_event_service.build_research_events(db, "intraday", 24)
        impacts = research_event_service.compute_asset_impacts(db, snapshot)
        portfolio = research_event_service.compute_user_portfolio_impacts(db, snapshot)
        return {
            "snapshot_id": snapshot.id,
            "events": snapshot.source_counts_json,
            "asset_impacts": impacts,
            "user_impacts": portfolio,
        }
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_earnings_calendar")
def sync_earnings_calendar() -> dict:
    from apps.api.services import research_event_service
    from packages.data import earnings_calendar
    from packages.data.earnings_calendar import ProviderUnavailable

    db = SessionLocal()
    try:
        today = utcnow().date()
        prefetched = 0
        provider_error = None
        try:
            # Warm the confirmed-earnings cache for today + 7 days; the research
            # build below reuses the same provider (and its cache).
            for offset in range(8):
                prefetched += len(earnings_calendar.fetch_confirmed_earnings(today + timedelta(days=offset)))
        except ProviderUnavailable as exc:
            provider_error = str(exc)[:300]
        snapshot = research_event_service.build_research_events(db, "earnings", 24)
        impacts = research_event_service.compute_asset_impacts(db, snapshot)
        portfolio = research_event_service.compute_user_portfolio_impacts(db, snapshot)
        return {
            "snapshot_id": snapshot.id,
            "prefetched": prefetched,
            "provider_error": provider_error,
            "events": snapshot.source_counts_json,
            "asset_impacts": impacts,
            "user_impacts": portfolio,
        }
    finally:
        db.close()


# =============================================================================
# LIVE Trading Control Plane background tasks (single-server budget).
# Every task is a cheap no-op when no LIVE mandate exists.
# =============================================================================


def _live_mandate_accounts(db) -> list:
    """(mandate, connection) pairs that are LIVE candidates."""
    from packages.database.models import BrokerConnection, TradingMandate

    mandates = (
        db.query(TradingMandate)
        .filter_by(execution_mode="live")
        .all()
    )
    pairs = []
    for mandate in mandates:
        connection = None
        if mandate.broker_connection_id:
            connection = (
                db.query(BrokerConnection)
                .filter_by(id=mandate.broker_connection_id)
                .one_or_none()
            )
        pairs.append((mandate, connection))
    return pairs


@celery_app.task(name="puregamma.refresh_live_market_prices")
def refresh_live_market_prices() -> dict:
    """Record server-side market prices for LIVE positions/whitelist (5-15s)."""
    db = SessionLocal()
    recorded = 0
    try:
        from apps.api.config import get_settings
        from packages.live_trading import ledger as ledger_service
        from packages.live_trading import price_feed as price_feed_service

        settings = get_settings()
        symbols: set[str] = set(settings.live_trading_allowed_symbols or ())
        client = NautilusRuntimeClient()
        for mandate, _connection in _live_mandate_accounts(db):
            quantities = ledger_service.position_quantities(db, mandate.account_id)
            symbols.update(q for q, v in quantities.items() if v != 0)
        if not symbols:
            return {"recorded": 0, "reason": "no symbols"}
        try:
            quotes = client.market_quotes(sorted(symbols), refresh=True).get("quotes", {})
        except Exception:
            logger.exception("live_market_price_refresh_failed")
            return {"recorded": 0, "reason": "runtime_unavailable"}
        for raw_symbol, quote in quotes.items():
            if isinstance(quote, dict):
                price = quote.get("price") or quote.get("last")
                if price is None:
                    continue
                price_feed_service.record_price(
                    db,
                    symbol=str(raw_symbol).upper(),
                    price=str(price),
                    venue=(quote.get("venue") or settings.live_trading_venue),
                    source="runtime",
                )
                recorded += 1
        db.commit()
        return {"recorded": recorded}
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_live_order_statuses")
def sync_live_order_statuses() -> dict:
    """Order status refresh (5-10s). UNKNOWN orders are QUERIED, never resubmitted."""
    db = SessionLocal()
    synced = 0
    try:
        from packages.database.models import LiveOrder
        from packages.live_trading.control_plane import sync_order_status

        orders = (
            db.query(LiveOrder)
            .filter(
                LiveOrder.status.in_(
                    ["pending", "submitted", "accepted", "partially_filled", "unknown"]
                )
            )
            .all()
        )
        for order in orders:
            try:
                sync_order_status(db, order)
                synced += 1
            except Exception:
                db.rollback()
                logger.exception("live_order_status_sync_failed order=%s", order.id)
        return {"synced": synced}
    finally:
        db.close()


@celery_app.task(name="puregamma.sync_live_balances_and_positions")
def sync_live_balances_and_positions() -> dict:
    """Balance/position refresh (30-60s): connection health + NAV trigger."""
    db = SessionLocal()
    checked = 0
    try:
        from packages.live_trading.control_plane import test_connection

        for mandate, connection in _live_mandate_accounts(db):
            if not connection:
                continue
            try:
                test_connection(db, connection.user_id, connection.id)
                checked += 1
            except Exception:
                db.rollback()
                continue
        return {"checked": checked}
    finally:
        db.close()


@celery_app.task(name="puregamma.calc_nav_for_account")
def calc_nav_for_account(user_id: str, account_id: str, mandate_id: str | None = None) -> dict:
    """NAV recalc for one account (triggered by fills and the periodic task)."""
    db = SessionLocal()
    try:
        from packages.live_trading.nav import calculate_nav

        snapshot = calculate_nav(db, user_id=user_id, account_id=account_id, mandate_id=mandate_id)
        db.commit()
        return {
            "snapshot_id": snapshot.id,
            "nav": str(snapshot.nav) if snapshot.nav is not None else None,
            "is_stale": snapshot.is_stale,
        }
    finally:
        db.close()


@celery_app.task(name="puregamma.calc_nav_for_active_accounts")
def calc_nav_for_active_accounts() -> dict:
    """Periodic NAV calculation for every LIVE account (30-60s)."""
    db = SessionLocal()
    computed = 0
    try:
        from packages.live_trading.nav import calculate_nav

        for mandate, _connection in _live_mandate_accounts(db):
            calculate_nav(
                db,
                user_id=mandate.user_id,
                account_id=mandate.account_id,
                mandate_id=mandate.id,
            )
            computed += 1
        db.commit()
        return {"computed": computed}
    finally:
        db.close()


@celery_app.task(name="puregamma.daily_live_reconciliation")
def daily_live_reconciliation() -> dict:
    """Daily exchange vs ledger vs NAV reconciliation.

    On difference: pause the mandate, forbid new orders, keep sync running,
    alert ops, and record the difference — never modify historical ledger."""
    db = SessionLocal()
    reconciled = 0
    try:
        from packages.live_trading.gateway_adapter import get_execution_gateway
        from packages.live_trading.reconciliation import reconcile_account
        from packages.live_trading.audit import new_trace_id

        gateway = get_execution_gateway()
        for mandate, connection in _live_mandate_accounts(db):
            try:
                reconcile_account(
                    db,
                    user_id=mandate.user_id,
                    account_id=mandate.account_id,
                    mandate=mandate,
                    connection=connection,
                    gateway=gateway,
                    trace_id=new_trace_id(),
                )
                reconciled += 1
            except Exception:
                db.rollback()
                logger.exception("live_reconciliation_failed mandate=%s", mandate.id)
        db.commit()
        return {"reconciled": reconciled}
    finally:
        db.close()
