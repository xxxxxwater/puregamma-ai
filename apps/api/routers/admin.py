from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db, require_admin
from apps.api.routers.auth import serialize_user
from apps.api.services.billing_service import resolve_checkout_intent, serialize_checkout_intent, stripe_products_status, sync_stripe_products
from apps.api.services.notification_service import serialize_delivery
from apps.api.services.data_source_service import provider_registry, serialize_run, serialize_source, sync_all_providers, sync_provider
from apps.api.services.report_service import serialize_report
from apps.api.config import get_settings
from packages.agents.llm.provider_factory import llm_status
from packages.database.models import AgentRun, AgentToolCall, BillingCheckoutIntent, DataSource, DataSourceSyncRun, FinTwitAccount, LLMCallLog, NormalizedDocument, NotificationDelivery, ProviderSyncLog, RawDocument, Report, StripeWebhookEvent, Subscription, User


router = APIRouter(prefix="/admin", tags=["admin"])


class ResolveIntentRequest(BaseModel):
    user_id: str
    plan_name: str


class DataSourceControlRequest(BaseModel):
    enabled: bool


class FinTwitAccountRequest(BaseModel):
    enabled: bool | None = None
    credibility_score: float | None = None
    account_weight: float | None = None
    provider_user_id: str | None = None


def admin_user(user: User = Depends(get_current_user)) -> User:
    require_admin(user)
    return user


@router.get("/users")
def users(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    return {"users": [serialize_user(row) for row in db.query(User).order_by(User.created_at.desc()).all()]}


@router.get("/reports")
def reports(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    return {"reports": [serialize_report(row) for row in db.query(Report).order_by(Report.created_at.desc()).limit(200).all()]}


@router.get("/data-sources")
def data_sources(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    rows = db.query(DataSource).order_by(DataSource.category, DataSource.name).all()
    return {"mockMode": False, "sources": [serialize_source(row, db, user.id) for row in rows]}


@router.patch("/data-sources/{provider_id}")
def control_data_source(provider_id: str, payload: DataSourceControlRequest, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    row = db.get(DataSource, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail="Data source not found")
    row.enabled = payload.enabled
    if not payload.enabled:
        row.status = "DISABLED"
    else:
        provider = provider_registry(db).get(provider_id)
        row.status = provider.health_check().status.value if provider else "ERROR"
    db.commit()
    return {"source": serialize_source(row, db, user.id)}


@router.post("/data-sources/{provider_id}/config-check")
def check_data_source_config(provider_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    row = db.get(DataSource, provider_id)
    provider = provider_registry(db).get(provider_id)
    if not row or not provider:
        raise HTTPException(status_code=404, detail="Data source not found")
    health = provider.health_check()
    row.status = health.status.value if row.enabled else "DISABLED"
    if health.status.value in {"ERROR", "DEGRADED", "NEEDS_KEY", "LICENSE_REQUIRED"}:
        row.last_error = health.message
    db.commit()
    return {"source": serialize_source(row, db, user.id), "check": {"status": health.status.value, "message": health.message, "details": health.details}}


@router.get("/data-sources/{provider_id}/preview")
def data_source_preview(provider_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    if not db.get(DataSource, provider_id):
        raise HTTPException(status_code=404, detail="Data source not found")
    raw_rows = db.query(RawDocument).filter(RawDocument.provider == provider_id).order_by(RawDocument.fetched_at.desc()).limit(20).all()
    normalized_rows = db.query(NormalizedDocument).filter(NormalizedDocument.provider == provider_id).order_by(NormalizedDocument.created_at.desc()).limit(20).all()
    return {
        "raw": [{"id": row.id, "externalId": row.external_id, "url": row.source_url, "publishedAt": row.published_at.isoformat() if row.published_at else None, "fetchedAt": row.fetched_at.isoformat(), "licenseStatus": row.license_status, "retentionPolicy": row.retention_policy, "processingStatus": row.processing_status, "payload": row.raw_payload} for row in raw_rows],
        "normalized": [{"id": row.id, "provider": row.provider, "sourceType": row.source_type, "sourceName": row.source_name, "title": row.title, "summary": row.summary, "url": row.url, "author": row.author, "publishedAt": row.published_at.isoformat() if row.published_at else None, "symbols": row.symbols, "topics": row.topics, "sentiment": row.sentiment, "credibilityScore": row.credibility_score, "finalScore": row.final_score, "licenseStatus": row.license_status, "retentionPolicy": row.retention_policy} for row in normalized_rows],
    }


@router.get("/data-sources/fintwit/accounts")
def fintwit_accounts(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    rows = db.query(FinTwitAccount).order_by(FinTwitAccount.category, FinTwitAccount.username).all()
    return {"accounts": [{"id": row.id, "username": row.username, "displayName": row.display_name, "platform": row.platform, "category": row.category, "language": row.language, "credibilityScore": row.credibility_score, "accountWeight": row.account_weight, "historicalAccuracy": row.historical_accuracy, "enabled": row.enabled, "sourceUrl": row.source_url, "providerUserId": row.provider_user_id, "collectionMethod": row.collection_method} for row in rows]}


@router.patch("/data-sources/fintwit/accounts/{account_id}")
def update_fintwit_account(account_id: str, payload: FinTwitAccountRequest, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    row = db.get(FinTwitAccount, account_id)
    if not row:
        raise HTTPException(status_code=404, detail="FinTwit account not found")
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.credibility_score is not None:
        row.credibility_score = max(0.0, min(1.0, payload.credibility_score))
    if payload.account_weight is not None:
        row.account_weight = max(0.0, min(2.0, payload.account_weight))
    if payload.provider_user_id is not None:
        row.provider_user_id = payload.provider_user_id or None
    db.commit()
    return {"account": {"id": row.id, "username": row.username, "enabled": row.enabled, "credibilityScore": row.credibility_score, "accountWeight": row.account_weight, "providerUserId": row.provider_user_id}}


@router.get("/data-sources/rss")
def rss_data_source(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    row = db.get(DataSource, "rss")
    return {"source": serialize_source(row) if row else None}


@router.post("/data-sources/rss/sync")
def sync_rss_data_source(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    return {"run": serialize_run(sync_provider(db, "rss", force=True))}


@router.post("/data-sources/sync-all")
def sync_all_data_sources(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    return {"runs": [serialize_run(row) for row in sync_all_providers(db)]}


@router.post("/data-sources/{provider_id}/sync")
def sync_data_source(provider_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    try:
        return {"run": serialize_run(sync_provider(db, provider_id, force=True))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/data-sources/{provider_id}/runs")
def data_source_runs(provider_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    if provider_id in {"rss", "fintwit", "x-twitter", "bloomberg"}:
        rows = db.query(ProviderSyncLog).filter(ProviderSyncLog.provider_id == provider_id).order_by(ProviderSyncLog.started_at.desc()).limit(100).all()
    else:
        rows = db.query(DataSourceSyncRun).filter(DataSourceSyncRun.provider_id == provider_id).order_by(DataSourceSyncRun.started_at.desc()).limit(100).all()
    return {"runs": [serialize_run(row) for row in rows]}


@router.get("/system-status")
def system_status(user: User = Depends(admin_user)) -> dict:
    settings = get_settings()
    llm = llm_status(settings)
    return {
        "database": "ok",
        "redis": "not_checked",
        "stripe_configured": bool(settings.stripe_secret_key),
        "stripe_webhook_secret_configured": bool(settings.stripe_webhook_secret),
        "billing_mode": settings.billing_mode,
        "billing_checkout_mode": settings.billing_checkout_mode,
        "deepseek_configured": bool(settings.deepseek_api_key),
        "llm_provider": llm["provider"],
        "llm_model": llm["model"],
        "imessage_status": settings.imessage_provider,
        "mock_mode": settings.billing_mode == "mock" or llm["active_provider"] == "mock",
    }


@router.get("/llm-status")
def admin_llm_status(user: User = Depends(admin_user)) -> dict:
    return llm_status(get_settings())


@router.get("/stripe-events")
def stripe_events(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    rows = db.query(StripeWebhookEvent).order_by(StripeWebhookEvent.created_at.desc()).limit(100).all()
    return {
        "stripe_events": [
            {
                "id": row.id,
                "stripe_event_id": row.stripe_event_id,
                "event_type": row.event_type,
                "processed": row.processed,
                "requires_manual_review": row.requires_manual_review,
                "error_message": row.error_message,
                "processed_at": row.processed_at.isoformat() if row.processed_at else None,
                "raw_payload_hash": row.raw_payload_hash,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.post("/stripe/products/sync")
def sync_stripe_product_catalog(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    try:
        return sync_stripe_products(db)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stripe/products")
def stripe_product_catalog_status(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    try:
        return stripe_products_status(db)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/billing-intents")
def billing_intents(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    rows = db.query(BillingCheckoutIntent).order_by(BillingCheckoutIntent.created_at.desc()).limit(200).all()
    return {"billing_intents": [serialize_checkout_intent(row) for row in rows]}


@router.post("/billing-intents/{intent_id}/resolve")
def resolve_billing_intent(intent_id: str, payload: ResolveIntentRequest, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    try:
        return {"billing_intent": resolve_checkout_intent(db, intent_id, payload.user_id, payload.plan_name, user.id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    rows = db.query(NotificationDelivery).order_by(NotificationDelivery.created_at.desc()).limit(200).all()
    return {"notifications": [serialize_delivery(row) for row in rows]}


@router.get("/subscriptions")
def subscriptions(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    rows = db.query(Subscription).order_by(Subscription.created_at.desc()).all()
    return {
        "subscriptions": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "plan_name": row.plan_name,
                "status": row.status,
                "stripe_customer_id": row.stripe_customer_id,
                "stripe_subscription_id": row.stripe_subscription_id,
            }
            for row in rows
        ]
    }


@router.get("/llm-calls")
def llm_calls(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    rows = db.query(LLMCallLog).order_by(LLMCallLog.created_at.desc()).limit(200).all()
    return {
        "llm_calls": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "provider": row.provider,
                "model": row.model,
                "task_type": row.task_type,
                "locale": row.locale,
                "prompt_summary": row.prompt_summary,
                "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens,
                "total_tokens": row.total_tokens,
                "estimated_cost_usd": row.estimated_cost_usd,
                "cache_hit": row.cache_hit,
                "status": row.status,
                "error_message": row.error_message,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/llm-cost-summary")
def llm_cost_summary(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    rows = db.query(LLMCallLog).all()
    summary: dict[str, dict] = {}
    for row in rows:
        bucket = summary.setdefault(row.provider, {"provider": row.provider, "calls": 0, "tokens": 0, "estimated_cost_usd": 0.0})
        bucket["calls"] += 1
        bucket["tokens"] += row.total_tokens
        bucket["estimated_cost_usd"] += row.estimated_cost_usd
    return {"summary": list(summary.values())}


def _serialize_agent_run(db: Session, row: AgentRun) -> dict:
    duration_ms = int(((row.completed_at or row.started_at) - row.started_at).total_seconds() * 1000)
    return {
        "id": row.id,
        "user_id": f"{row.user_id[:8]}...",
        "conversation_id": row.conversation_id,
        "model": row.model,
        "status": row.status,
        "duration_ms": duration_ms,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "tool_calls_count": row.tool_calls_count,
        "error": row.error_message,
        "trace_id": row.trace_id,
        "created_at": row.started_at.isoformat(),
    }


@router.get("/agent/runs")
def agent_runs(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    rows = db.query(AgentRun).order_by(AgentRun.started_at.desc()).limit(200).all()
    return {"runs": [_serialize_agent_run(db, row) for row in rows]}


@router.get("/agent/runs/{run_id}")
def agent_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    row = db.get(AgentRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Agent run not found")
    tool_calls = db.query(AgentToolCall).filter_by(run_id=row.id).order_by(AgentToolCall.created_at).all()
    return {"run": _serialize_agent_run(db, row), "tool_calls": [{"id": call.id, "tool_name": call.tool_name, "status": call.status, "result_summary": call.result_summary, "latency_ms": call.latency_ms, "error": call.error_message, "created_at": call.created_at.isoformat()} for call in tool_calls]}
