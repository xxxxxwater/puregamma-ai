from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db
from apps.api.services import billing_service
from packages.database.models import User
from apps.api.services.entitlement_service import get_user_entitlement
from apps.api.services.credit_service import quote_task


router = APIRouter(prefix="/billing", tags=["billing"])


class PlanRequest(BaseModel):
    plan_name: str

class QuoteRequest(BaseModel):
    task_type: str = "default_chat"
    requested_model: str = "default"
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    attachment_bytes: int = Field(default=0, ge=0)
    tool_calls: list[str] = []
    selected_data_sources: list[str] = []
    async_execution: bool = False
    notification_channel: str | None = None


class BudgetRequest(BaseModel):
    daily_limit: int = Field(ge=1, le=100_000)
    monthly_limit: int = Field(ge=1, le=1_000_000)
    per_run_limit: int = Field(ge=1, le=10_000)
    alert_threshold_pct: int = Field(default=80, ge=1, le=100)
    enabled: bool = True

@router.get("/subscription")
def subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return billing_service.get_subscription(db, user.id)


@router.get("/credits")
def credits(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return billing_service.get_credits(db, user.id)

@router.get("/ledger")
def ledger(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    from packages.database.models import CreditLedger
    rows = db.query(CreditLedger).filter_by(user_id=user.id).order_by(CreditLedger.created_at.desc()).limit(200).all()
    return {"credit_balance": user.credit_balance, "entries": [{"id": row.id, "action": row.action, "credits_delta": row.credits_delta, "balance_after": row.balance_after, "metadata": row.metadata_json, "created_at": row.created_at.isoformat()} for row in rows]}


@router.get("/budget")
def budget(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    from packages.billing.budgets import budget_snapshot

    return {"budgets": budget_snapshot(db, user)}


@router.put("/budget/{automation_key}")
def update_budget(
    automation_key: str,
    payload: BudgetRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    from packages.billing.budgets import budget_snapshot, get_or_create_policy

    if not automation_key.replace("_", "").replace("-", "").isalnum() or len(automation_key) > 120:
        raise HTTPException(status_code=400, detail={"code": "AUTOMATION_KEY_INVALID"})
    if payload.per_run_limit > payload.daily_limit or payload.daily_limit > payload.monthly_limit:
        raise HTTPException(status_code=400, detail={"code": "AUTOMATION_BUDGET_INVALID"})
    locked_user = db.query(User).filter(User.id == user.id).with_for_update().one()
    row = get_or_create_policy(db, locked_user, automation_key)
    row.daily_limit = payload.daily_limit
    row.monthly_limit = payload.monthly_limit
    row.per_run_limit = payload.per_run_limit
    row.alert_threshold_pct = payload.alert_threshold_pct
    row.enabled = payload.enabled
    if payload.enabled:
        row.paused = False
        row.pause_reason = None
    db.commit()
    return {"budgets": budget_snapshot(db, locked_user)}


@router.get("/rewards")
def rewards(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    from packages.database.models import CreditRewardGrant

    rows = db.query(CreditRewardGrant).filter_by(user_id=user.id).order_by(CreditRewardGrant.created_at.desc()).limit(200).all()
    return {"rewards": [{"id": row.id, "reward_type": row.reward_type, "credits": row.credits, "source": row.source, "metadata": row.metadata_json, "created_at": row.created_at.isoformat()} for row in rows]}

@router.post("/quote")
def quote(
    payload: QuoteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    allowed_tasks = {
        "agent_chat_basic",
        "agent_market_research",
        "agent_news_research",
        "agent_portfolio_analysis",
        "agent_advanced_data",
        "agent_deep_research",
        "agent_luna_research",
        "default_chat",
        "default_deep_research",
        "luna_research",
        "luna_deep_research",
        "daily_market_report",
        "portfolio_daily_brief",
        "email_alert",
        "telegram_alert",
        "imessage_alert",
    }
    if payload.task_type not in allowed_tasks:
        raise HTTPException(status_code=400, detail={"code": "BILLING_TASK_INVALID"})
    settings = get_settings()
    requested_model = payload.requested_model or "default"
    if requested_model not in {"default", settings.openai_luna_model}:
        raise HTTPException(status_code=400, detail={"code": "AGENT_MODEL_INVALID"})
    entitlement = get_user_entitlement(db, user.id)
    if requested_model == settings.openai_luna_model:
        allowed_plans = {name.lower() for name in settings.openai_luna_allowed_plans}
        if entitlement["plan"].lower() not in allowed_plans:
            raise HTTPException(status_code=403, detail={"code": "AGENT_MODEL_PLAN_REQUIRED"})
        if not settings.openai_luna_enabled or not settings.openai_api_key:
            raise HTTPException(status_code=503, detail={"code": "AGENT_MODEL_UNAVAILABLE"})
    allowed_sources = set(entitlement["allowed_data_sources"])
    selected_sources = payload.selected_data_sources
    if "all" not in allowed_sources:
        selected_sources = [source for source in selected_sources if source in allowed_sources]
    result = quote_task(
        **payload.model_dump(exclude={"selected_data_sources"}),
        resolved_model=requested_model,
        selected_data_sources=selected_sources,
    )
    return {"estimated_min": result.credits, "estimated_max": result.credits,
            "reservation_amount": result.credits, "pricing_version": "metering-v1", "quote": result.__dict__}


@router.get("/capabilities")
def capabilities(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"capabilities": get_user_entitlement(db, user.id)}


@router.post("/create-checkout-session")
def checkout(payload: PlanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        result = billing_service.create_checkout_session(db, user.id, payload.plan_name)
        db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/create-payment-link-checkout")
def payment_link_checkout(payload: PlanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        result = billing_service.create_payment_link_checkout(db, user.id, payload.plan_name)
        db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/create-portal-session")
def portal(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return billing_service.create_portal_session(db, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cancel-subscription")
def cancel_subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return billing_service.set_subscription_cancel_at_period_end(db, user.id, True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reactivate-subscription")
def reactivate_subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return billing_service.set_subscription_cancel_at_period_end(db, user.id, False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mock-upgrade")
def mock_upgrade(payload: PlanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    settings = get_settings()
    # Mock upgrades are a developer-only convenience: they must never be
    # reachable in production, and also not when billing is wired to Stripe
    # (a misconfigured APP_ENV must not silently grant paid entitlements).
    if settings.app_environment.lower() == "production" or settings.billing_mode != "mock":
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return billing_service.mock_upgrade(db, user.id, payload.plan_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
