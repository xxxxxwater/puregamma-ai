from __future__ import annotations

from datetime import timedelta

from apps.api.services.market_intelligence_service import generate_shared_market_intelligence
from apps.api.services.notification_service import send_notification
from apps.api.services.report_service import create_daily_report
from apps.api.services.signal_service import scan_signals
from apps.api.services.data_source_service import sync_all_providers, sync_provider
from apps.api.config import get_settings
from packages.database.models import RawDocument, User, utcnow
from packages.database.session import SessionLocal
from packages.workers.celery_app import celery_app


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
                language = getattr(user.preference, "locale", "en") if user.preference else "en"
                ids.append(create_daily_report(db, user.id, language).id)
            except Exception:
                db.rollback()
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
        users = db.query(User).all()
        for user in users:
            pref = user.preference
            if not pref:
                continue
            language = getattr(pref, "locale", "en")
            message = "PureGamma.ai 每日报告已生成。This is not financial advice." if language == "zh" else "PureGamma.ai daily report is ready. This is not financial advice."
            for channel in pref.notification_channels:
                try:
                    delivery = send_notification(
                        db,
                        user.id,
                        channel,
                        message,
                        {"idempotency_key": f"daily-{user.id}-{channel}-{language}", "locale": language},
                    )
                    sent += 1 if delivery.status == "sent" else 0
                except Exception:
                    db.rollback()
        return sent
    finally:
        db.close()


@celery_app.task(name="puregamma.check_subscription_status")
def check_subscription_status() -> str:
    return "subscription_status_check_delegated_to_stripe_webhooks"


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
        return [{"id": row.id, "provider": row.provider_id, "status": row.status} for row in sync_all_providers(db)]
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
