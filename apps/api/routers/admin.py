from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import cast, func, or_, String
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db, require_admin
from apps.api.routers.auth import serialize_user
from apps.api.services.billing_service import resolve_checkout_intent, serialize_checkout_intent, stripe_products_status, sync_stripe_products
from apps.api.services.notification_service import serialize_delivery
from apps.api.services.data_source_service import provider_registry, redact_error, serialize_run, serialize_source, sync_all_providers, sync_provider
from apps.api.services.report_service import serialize_report
from apps.api.config import get_settings
from packages.agents.llm.provider_factory import llm_status
from packages.database.models import (
    AccountSnapshot,
    AgentRun,
    AgentToolCall,
    Alert,
    AssetImpact,
    BacktestRun,
    BillingCheckoutIntent,
    CreditLedger,
    CreditRefundEvent,
    CreditReservationRecord,
    CreditRewardGrant,
    CreditSettlementRecord,
    CustodyAccount,
    CustodyDeposit,
    CustodyLedgerEntry,
    CustodyReconciliation,
    CustodySubAccount,
    CustodyWithdrawal,
    DataSource,
    DataSourceSyncRun,
    ExchangeConnection,
    FinTwitAccount,
    LLMCallLog,
    MarketEvent,
    NormalizedDocument,
    NotificationDelivery,
    OrderIntent,
    OrderJournal,
    PositionSnapshot,
    ProviderSyncLog,
    RawDocument,
    ReconciliationRecord,
    Report,
    ResearchAction,
    ResearchSnapshot,
    RiskDecision,
    Skill,
    SkillRun,
    StrategyRun,
    StripeWebhookEvent,
    Subscription,
    TradingStrategy,
    User,
    UserPortfolioImpact,
)


router = APIRouter(prefix="/admin", tags=["admin"])


class ResolveIntentRequest(BaseModel):
    user_id: str
    plan_name: str


class AdminRewardGrantRequest(BaseModel):
    user_id: str
    reward_type: str = "manual_admin_grant"
    credits: int = Field(ge=1, le=5000)
    idempotency_key: str = Field(min_length=8, max_length=200)
    source: str = Field(default="admin_console", min_length=1, max_length=120)
    metadata: dict = Field(default_factory=dict)


class AdminCreditGrantRequest(BaseModel):
    credits: int = Field(ge=1, le=5000)
    reason: str = Field(min_length=3, max_length=300)
    reference: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=8, max_length=200)


class AdminCreditRefundRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)
    reference: str = Field(min_length=3, max_length=120)


class AdminPlanUpdateRequest(BaseModel):
    plan: str = Field(min_length=2, max_length=20)


class AdminTierUpdateRequest(BaseModel):
    tier: str = Field(min_length=3, max_length=10)


class AdminCreditAdjustRequest(BaseModel):
    credits: int = Field(ge=-5000, le=5000)
    reason: str = Field(min_length=3, max_length=300)
    reference: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=8, max_length=200)


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


def _admin_credit_metadata(metadata: dict | None) -> dict:
    """Expose operational audit fields without returning stored prompts or provider payloads."""
    allowed = {
        "source",
        "reason",
        "reference",
        "ticket",
        "phase",
        "reservation_id",
        "granted_by_user_id",
        "refunded_by_user_id",
        "original_ledger_entry_id",
        "task_type",
    }
    return {key: value for key, value in (metadata or {}).items() if key in allowed}


def _serialize_admin_ledger(row: CreditLedger, refunded_entry_ids: set[str] | None = None) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "credits_delta": row.credits_delta,
        "balance_after": row.balance_after,
        "idempotency_key": row.idempotency_key,
        "metadata": _admin_credit_metadata(row.metadata_json),
        "refundable": row.credits_delta < 0 and row.id not in (refunded_entry_ids or set()),
        "created_at": row.created_at.isoformat(),
    }


def _serialize_admin_reservation(row: CreditReservationRecord) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "task_type": row.task_type,
        "status": row.status,
        "reserved_credits": row.reserved_credits,
        "settled_credits": row.settled_credits,
        "idempotency_key": row.idempotency_key,
        "refundable": row.status == "RESERVED",
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


@router.get("/users")
def users(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    return {"users": [serialize_user(row) for row in db.query(User).order_by(User.created_at.desc()).all()]}


@router.get("/billing/accounts")
def billing_accounts(
    search: str = Query(default="", max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    query = db.query(User)
    normalized = search.strip()
    if normalized:
        pattern = f"%{normalized}%"
        query = query.filter((User.email.ilike(pattern)) | (User.name.ilike(pattern)) | (User.id == normalized))
    total = query.count()
    rows = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "accounts": [
            {
                "id": row.id,
                "email": row.email,
                "name": row.name,
                "role": row.role,
                "plan": row.plan,
                "membership_tier": row.membership_tier,
                "credit_balance": row.credit_balance,
                "stripe_customer_id": row.stripe_customer_id,
                "auth_provider": row.auth_provider,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/billing/accounts/{user_id}")
def billing_account(user_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    from apps.api.services.credit_service import reconcile_credit_account

    account = db.get(User, user_id)
    if not account:
        raise HTTPException(status_code=404, detail="User not found")
    ledger_rows = (
        db.query(CreditLedger)
        .filter(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.created_at.desc(), CreditLedger.id.desc())
        .limit(200)
        .all()
    )
    non_refundable_entry_ids = {
        str(row.metadata_json.get("original_ledger_entry_id"))
        for row in ledger_rows
        if row.action == "admin_credit_refund" and row.metadata_json.get("original_ledger_entry_id")
    }
    reservations = (
        db.query(CreditReservationRecord)
        .filter(CreditReservationRecord.user_id == user_id)
        .order_by(CreditReservationRecord.created_at.desc())
        .limit(100)
        .all()
    )
    non_refundable_entry_ids.update(
        row.ledger_entry_id for row in reservations if not row.status.startswith("SETTLED")
    )
    settlements = (
        db.query(CreditSettlementRecord)
        .filter(CreditSettlementRecord.user_id == user_id)
        .order_by(CreditSettlementRecord.created_at.desc())
        .limit(100)
        .all()
    )
    refunds = (
        db.query(CreditRefundEvent)
        .filter(CreditRefundEvent.user_id == user_id)
        .order_by(CreditRefundEvent.created_at.desc())
        .limit(100)
        .all()
    )
    rewards = (
        db.query(CreditRewardGrant)
        .filter(CreditRewardGrant.user_id == user_id)
        .order_by(CreditRewardGrant.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "account": {
            "id": account.id,
            "email": account.email,
            "name": account.name,
            "role": account.role,
            "plan": account.plan,
            "membership_tier": account.membership_tier,
            "credit_balance": account.credit_balance,
            "stripe_customer_id": account.stripe_customer_id,
            "auth_provider": account.auth_provider,
            "created_at": account.created_at.isoformat(),
            "updated_at": account.updated_at.isoformat(),
        },
        "reconciliation": reconcile_credit_account(db, user_id),
        "ledger": [_serialize_admin_ledger(row, non_refundable_entry_ids) for row in ledger_rows],
        "reservations": [_serialize_admin_reservation(row) for row in reservations],
        "settlements": [
            {
                "id": row.id,
                "reservation_id": row.reservation_id,
                "requested_actual_credits": row.requested_actual_credits,
                "settled_credits": row.settled_credits,
                "adjustment": row.adjustment,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
            }
            for row in settlements
        ],
        "refunds": [
            {
                "id": row.id,
                "reservation_id": row.reservation_id,
                "credits": row.credits,
                "reason": row.reason,
                "created_at": row.created_at.isoformat(),
            }
            for row in refunds
        ],
        "rewards": [
            {
                "id": row.id,
                "reward_type": row.reward_type,
                "credits": row.credits,
                "source": row.source,
                "granted_by_user_id": row.granted_by_user_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in rewards
        ],
    }


@router.post("/billing/accounts/{user_id}/credits/grant")
def grant_account_credits(
    user_id: str,
    payload: AdminCreditGrantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from packages.billing.rewards import grant_reward

    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    try:
        row = grant_reward(
            db,
            user_id,
            "manual_admin_grant",
            payload.credits,
            idempotency_key=payload.idempotency_key,
            source="admin_credit_console",
            metadata={"reason": payload.reason, "reference": payload.reference},
            granted_by_user_id=user.id,
        )
        if row.user_id != user_id:
            raise ValueError("Idempotency key belongs to another user")
        db.commit()
        account = db.get(User, user_id)
        return {
            "grant": {
                "id": row.id,
                "credits": row.credits,
                "reason": row.metadata_json.get("reason"),
                "reference": row.metadata_json.get("reference"),
                "granted_by_user_id": row.granted_by_user_id,
                "created_at": row.created_at.isoformat(),
            },
            "credit_balance": account.credit_balance,
        }
    except (ValueError, LookupError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/users/{user_id}/plan")
def update_user_plan(
    user_id: str,
    payload: AdminPlanUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    allowed_plans = {"Free", "Pro", "Max", "Enterprise"}
    if payload.plan not in allowed_plans:
        raise HTTPException(status_code=400, detail=f"Plan must be one of: {', '.join(sorted(allowed_plans))}")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own plan")
    old_plan = target.plan
    target.plan = payload.plan
    db.commit()
    return {
        "user_id": target.id,
        "email": target.email,
        "plan": target.plan,
        "previous_plan": old_plan,
    }


@router.patch("/users/{user_id}/tier")
def update_user_tier(
    user_id: str,
    payload: AdminTierUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from packages.billing.plans import plan_for_tier

    allowed_tiers = {"silver", "gold"}
    if payload.tier not in allowed_tiers:
        raise HTTPException(
            status_code=400,
            detail=f"Tier must be one of: {', '.join(sorted(allowed_tiers))}",
        )
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own tier")
    # Subscription priority: an active/trialing Stripe subscription is
    # authoritative. Admin must change or cancel the subscription in Stripe
    # rather than override the tier here (no silent double bookkeeping).
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == target.id)
        .order_by(Subscription.created_at.desc())
        .first()
    )
    if sub and sub.status in {"active", "trialing"} and sub.plan_name not in {
        "Free",
        "Invite Preview",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                f"User has an active Stripe subscription ({sub.plan_name}); "
                "change or cancel the subscription in Stripe first"
            ),
        )
    old_tier = target.membership_tier
    target.membership_tier = payload.tier
    # For users without a Stripe subscription, the tier defines the membership:
    # keep user.plan in sync so entitlements and every surface stay consistent.
    target.plan = plan_for_tier(payload.tier)
    db.commit()
    return {
        "user_id": target.id,
        "email": target.email,
        "tier": target.membership_tier,
        "previous_tier": old_tier,
        "plan": target.plan,
    }


@router.post("/users/{user_id}/credits/adjust")
def adjust_user_credits(
    user_id: str,
    payload: AdminCreditAdjustRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.credits == 0:
        raise HTTPException(status_code=400, detail="Credits must be non-zero")

    amount = payload.credits
    action = "admin_credit_grant" if amount > 0 else "admin_credit_deduction"
    abs_amount = abs(amount)

    if amount < 0 and target.credit_balance + amount < 0:
        raise HTTPException(status_code=400, detail=f"Insufficient balance. Current: {target.credit_balance}, attempted deduction: {abs_amount}")

    existing = db.query(CreditLedger).filter_by(idempotency_key=payload.idempotency_key).one_or_none()
    if existing:
        if existing.user_id != user_id:
            raise HTTPException(status_code=400, detail="Idempotency key belongs to another user")
        return {
            "adjustment": {
                "id": existing.id,
                "action": existing.action,
                "credits_delta": existing.credits_delta,
                "balance_after": existing.balance_after,
                "reason": existing.metadata_json.get("reason"),
                "reference": existing.metadata_json.get("reference"),
                "created_at": existing.created_at.isoformat(),
            },
            "credit_balance": existing.balance_after,
        }

    try:
        target.credit_balance = int(target.credit_balance) + amount
        ledger_entry = CreditLedger(
            user_id=user_id,
            action=action,
            credits_delta=amount,
            balance_after=target.credit_balance,
            metadata_json={
                "source": "admin_user_manager",
                "reason": payload.reason,
                "reference": payload.reference,
                "granted_by_user_id": user.id,
            },
            idempotency_key=payload.idempotency_key,
        )
        db.add(ledger_entry)
        db.commit()
        return {
            "adjustment": {
                "id": ledger_entry.id,
                "action": action,
                "credits_delta": amount,
                "balance_after": ledger_entry.balance_after,
                "reason": payload.reason,
                "reference": payload.reference,
                "created_at": ledger_entry.created_at.isoformat(),
            },
            "credit_balance": ledger_entry.balance_after,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/billing/reservations/{reservation_id}/refund")
def refund_credit_reservation(
    reservation_id: str,
    payload: AdminCreditRefundRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from apps.api.services.credit_service import refund_task
    from packages.billing.metering import CreditReservation

    row = db.get(CreditReservationRecord, reservation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Credit reservation not found")
    try:
        result = refund_task(
            db,
            row.user_id,
            CreditReservation(idempotency_key=row.idempotency_key, credits=row.reserved_credits),
            payload.reason,
            {
                "source": "admin_credit_console",
                "reference": payload.reference,
                "refunded_by_user_id": user.id,
            },
        )
        db.commit()
        account = db.get(User, row.user_id)
        return {
            "refund": {"reservation_id": row.id, "credits": result.adjustment, "status": row.status},
            "credit_balance": account.credit_balance,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/billing/ledger/{entry_id}/refund")
def refund_credit_ledger_entry(
    entry_id: str,
    payload: AdminCreditRefundRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from apps.api.services.credit_service import grant_credits

    entry = db.get(CreditLedger, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Credit ledger entry not found")
    if entry.credits_delta >= 0:
        raise HTTPException(status_code=409, detail="Only a debit ledger entry can be refunded")
    refund_key = f"admin-ledger-refund:{entry.id}"
    reservation = db.query(CreditReservationRecord).filter_by(ledger_entry_id=entry.id).one_or_none()
    if reservation and reservation.status == "RESERVED":
        raise HTTPException(status_code=409, detail="Open reservation must be refunded through the reservation state machine")
    if reservation and reservation.status == "REFUNDED":
        raise HTTPException(status_code=409, detail="Reservation has already been refunded")
    amount = abs(entry.credits_delta)
    if reservation and reservation.status.startswith("SETTLED"):
        amount = min(amount, max(0, int(reservation.settled_credits or 0)))
    if amount <= 0:
        raise HTTPException(status_code=409, detail="Ledger entry has no refundable settled credits")
    try:
        ledger = grant_credits(
            db,
            entry.user_id,
            "admin_credit_refund",
            amount,
            {
                "source": "admin_credit_console",
                "reason": payload.reason,
                "reference": payload.reference,
                "refunded_by_user_id": user.id,
                "original_ledger_entry_id": entry.id,
            },
            idempotency_key=refund_key,
        )
        db.commit()
        account = db.get(User, entry.user_id)
        return {
            "refund": {
                "ledger_entry_id": entry.id,
                "refund_ledger_entry_id": ledger.id,
                "credits": ledger.credits_delta,
                "reason": ledger.metadata_json.get("reason"),
                "reference": ledger.metadata_json.get("reference"),
            },
            "credit_balance": account.credit_balance,
        }
    except (ValueError, LookupError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/billing/rewards/grant")
def grant_billing_reward(
    payload: AdminRewardGrantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from packages.billing.rewards import grant_reward

    try:
        row = grant_reward(
            db,
            payload.user_id,
            payload.reward_type,
            payload.credits,
            idempotency_key=payload.idempotency_key,
            source=payload.source,
            metadata=payload.metadata,
            granted_by_user_id=user.id,
        )
        db.commit()
        return {
            "grant": {
                "id": row.id,
                "user_id": row.user_id,
                "reward_type": row.reward_type,
                "credits": row.credits,
                "source": row.source,
                "idempotency_key": row.idempotency_key,
                "granted_by_user_id": row.granted_by_user_id,
                "created_at": row.created_at.isoformat(),
            }
        }
    except (ValueError, LookupError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reports")
def reports(
    status: str | None = Query(default=None, max_length=40),
    user_id: str | None = Query(default=None, max_length=64),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    query = db.query(Report)
    if status:
        query = query.filter(Report.status == status)
    if user_id:
        query = query.filter(Report.user_id == user_id)
    if date_from:
        query = query.filter(Report.created_at >= date_from)
    if date_to:
        query = query.filter(Report.created_at <= date_to)
    total = query.count()
    rows = query.order_by(Report.created_at.desc(), Report.id.desc()).offset(offset).limit(limit).all()
    return {"reports": [serialize_report(row) for row in rows], "total": total, "limit": limit, "offset": offset}


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
def llm_calls(
    provider: str | None = Query(default=None, max_length=60),
    model: str | None = Query(default=None, max_length=120),
    task_type: str | None = Query(default=None, max_length=60),
    status: str | None = Query(default=None, max_length=40),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    filters = []
    if provider:
        filters.append(LLMCallLog.provider == provider)
    if model:
        filters.append(LLMCallLog.model == model)
    if task_type:
        filters.append(LLMCallLog.task_type == task_type)
    if status:
        filters.append(LLMCallLog.status == status)
    if date_from:
        filters.append(LLMCallLog.created_at >= date_from)
    if date_to:
        filters.append(LLMCallLog.created_at <= date_to)
    query = db.query(LLMCallLog).filter(*filters)
    total = query.count()
    rows = query.order_by(LLMCallLog.created_at.desc(), LLMCallLog.id.desc()).offset(offset).limit(limit).all()
    aggregate_rows = (
        db.query(
            LLMCallLog.provider,
            LLMCallLog.model,
            func.count().label("calls"),
            func.avg(LLMCallLog.latency_ms).label("avg_latency_ms"),
            func.coalesce(func.sum(LLMCallLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LLMCallLog.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(LLMCallLog.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(LLMCallLog.estimated_cost_usd), 0.0).label("estimated_cost_usd"),
        )
        .filter(*filters)
        .group_by(LLMCallLog.provider, LLMCallLog.model)
        .order_by(LLMCallLog.provider, LLMCallLog.model)
        .all()
    )
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
                "latency_ms": row.latency_ms,
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ],
        "aggregates": [
            {
                "provider": row.provider,
                "model": row.model,
                "calls": int(row.calls),
                "avg_latency_ms": round(float(row.avg_latency_ms), 1) if row.avg_latency_ms is not None else None,
                "prompt_tokens": int(row.prompt_tokens or 0),
                "completion_tokens": int(row.completion_tokens or 0),
                "total_tokens": int(row.total_tokens or 0),
                "estimated_cost_usd": float(row.estimated_cost_usd or 0.0),
            }
            for row in aggregate_rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/llm-cost-summary")
def llm_cost_summary(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    # Aggregate in the database instead of scanning the whole table into memory.
    rows = (
        db.query(
            LLMCallLog.provider,
            func.count().label("calls"),
            func.coalesce(func.sum(LLMCallLog.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(LLMCallLog.estimated_cost_usd), 0.0).label("estimated_cost_usd"),
        )
        .group_by(LLMCallLog.provider)
        .all()
    )
    summary = [
        {"provider": provider, "calls": calls, "tokens": int(tokens or 0), "estimated_cost_usd": float(cost or 0.0)}
        for provider, calls, tokens, cost in rows
    ]
    return {"summary": summary}


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


# ---------------------------------------------------------------------------
# P0-12 admin console: read-only operational observation surfaces.
# Every payload is built from whitelisted columns only — credential material
# (api keys, ciphertext, tokens) is never serialized. Timestamps are UTC ISO.
# ---------------------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _num(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _latest_completed_snapshot(db: Session) -> ResearchSnapshot | None:
    return (
        db.query(ResearchSnapshot)
        .filter(ResearchSnapshot.status == "completed")
        .order_by(ResearchSnapshot.as_of.desc())
        .first()
    )


def _source_health(db: Session, snapshot: ResearchSnapshot | None) -> list[dict]:
    """Per-source health: DataSource rows merged with the latest research snapshot health."""
    health: dict[str, dict] = {}
    for row in db.query(DataSource).order_by(DataSource.category, DataSource.name).all():
        health[row.id] = {
            "id": row.id,
            "name": row.name,
            "category": row.category,
            "provider": row.provider,
            "status": row.status,
            "enabled": row.enabled,
            "last_sync_at": _iso(row.last_sync_at),
            "last_success_at": _iso(row.last_success_at),
            "error": redact_error(row.last_error),
            "items": row.item_count,
            "research": None,
        }
    if snapshot and isinstance(snapshot.health_json, dict):
        for name, raw_info in snapshot.health_json.items():
            info = raw_info if isinstance(raw_info, dict) else {}
            research = {
                "status": info.get("status"),
                "last_success_at": info.get("last_success_at"),
                "error": info.get("error"),
                "items": info.get("items", 0),
            }
            entry = health.get(name)
            if entry is None:
                entry = {
                    "id": name,
                    "name": name,
                    "category": "research",
                    "provider": name,
                    "status": "NOT_CONNECTED",
                    "enabled": True,
                    "last_sync_at": None,
                    "last_success_at": None,
                    "error": None,
                    "items": 0,
                    "research": None,
                }
                health[name] = entry
            entry["research"] = research
            if not entry["last_success_at"] and research["last_success_at"]:
                entry["last_success_at"] = research["last_success_at"]
            if not entry["error"] and research["error"]:
                entry["error"] = research["error"]
            if not entry["items"] and research["items"]:
                entry["items"] = research["items"]
    return sorted(health.values(), key=lambda item: item["id"])


def _serialize_snapshot_brief(snapshot: ResearchSnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    return {
        "id": snapshot.id,
        "kind": snapshot.kind,
        "as_of": _iso(snapshot.as_of),
        "data_cutoff_at": _iso(snapshot.data_cutoff_at),
        "status": snapshot.status,
        "source_counts": snapshot.source_counts_json,
    }


def _serialize_admin_delivery(row: NotificationDelivery) -> dict:
    payload = row.payload if isinstance(row.payload, dict) else {}
    return {
        "id": row.id,
        "user_id": row.user_id,
        "channel": row.channel,
        "status": row.status,
        "locale": row.locale,
        "retry_count": row.retry_count,
        "attempt_count": row.attempt_count,
        "last_attempt_at": _iso(row.last_attempt_at),
        "next_retry_at": _iso(row.next_retry_at),
        "last_error": row.last_error,
        "idempotency_key": row.idempotency_key,
        "report_id": payload.get("report_id"),
        "created_at": _iso(row.created_at),
        "sent_at": _iso(row.sent_at),
    }


def _serialize_connection(row: ExchangeConnection) -> dict:
    """Whitelist only — never credential_reference / credential_ciphertext."""
    return {
        "id": row.id,
        "user_id": row.user_id,
        "account_id": row.account_id,
        "adapter": row.adapter,
        "environment": row.environment,
        "status": row.status,
        "last_health_at": _iso(row.last_health_at),
        "error_code": row.error_code,
        "error_message": row.error_message,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    snapshot = _latest_completed_snapshot(db)
    return {
        "generated_at": now.isoformat(),
        "counts": {
            "users": db.query(User).count(),
            "reports": db.query(Report).count(),
            "events": db.query(MarketEvent).count(),
            "alerts": db.query(Alert).count(),
            "deliveries_failed_24h": db.query(NotificationDelivery)
            .filter(NotificationDelivery.status == "failed", NotificationDelivery.created_at >= day_ago)
            .count(),
            "llm_calls_24h": db.query(LLMCallLog).filter(LLMCallLog.created_at >= day_ago).count(),
            "active_strategies": db.query(TradingStrategy).filter(TradingStrategy.status == "ACTIVE").count(),
            "custody_accounts": db.query(CustodyAccount).count(),
        },
        "snapshot": _serialize_snapshot_brief(snapshot),
        "source_health": _source_health(db, snapshot),
    }


@router.get("/users/{user_id}")
def admin_user_detail(user_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    account = db.get(User, user_id)
    if not account:
        raise HTTPException(status_code=404, detail="User not found")
    ledger = (
        db.query(CreditLedger)
        .filter(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.created_at.desc(), CreditLedger.id.desc())
        .limit(20)
        .all()
    )
    subscriptions = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .limit(20)
        .all()
    )
    connections = (
        db.query(ExchangeConnection)
        .filter(ExchangeConnection.user_id == user_id)
        .order_by(ExchangeConnection.updated_at.desc())
        .limit(20)
        .all()
    )
    reports = (
        db.query(Report)
        .filter(Report.user_id == user_id)
        .order_by(Report.created_at.desc())
        .limit(10)
        .all()
    )
    deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.user_id == user_id)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(10)
        .all()
    )
    agent_runs = (
        db.query(AgentRun)
        .filter(AgentRun.user_id == user_id)
        .order_by(AgentRun.started_at.desc())
        .limit(10)
        .all()
    )
    return {
        "user": serialize_user(account),
        "plan": account.plan,
        "membership_tier": account.membership_tier,
        "credits": {
            "balance": account.credit_balance,
            "recent_ledger": [_serialize_admin_ledger(row) for row in ledger],
        },
        "subscriptions": [
            {
                "id": row.id,
                "plan_name": row.plan_name,
                "status": row.status,
                "stripe_customer_id": row.stripe_customer_id,
                "stripe_subscription_id": row.stripe_subscription_id,
                "current_period_start": _iso(row.current_period_start),
                "current_period_end": _iso(row.current_period_end),
                "cancel_at_period_end": row.cancel_at_period_end,
                "created_at": _iso(row.created_at),
            }
            for row in subscriptions
        ],
        "connections": [_serialize_connection(row) for row in connections],
        "reports": [serialize_report(row) for row in reports],
        "deliveries": [_serialize_admin_delivery(row) for row in deliveries],
        "agent_runs": [_serialize_agent_run(db, row) for row in agent_runs],
    }


@router.get("/deliveries")
def admin_deliveries(
    status: str | None = Query(default=None, max_length=40),
    channel: str | None = Query(default=None, max_length=40),
    user_id: str | None = Query(default=None, max_length=64),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    query = db.query(NotificationDelivery)
    if status:
        query = query.filter(NotificationDelivery.status == status)
    if channel:
        query = query.filter(NotificationDelivery.channel == channel)
    if user_id:
        query = query.filter(NotificationDelivery.user_id == user_id)
    if date_from:
        query = query.filter(NotificationDelivery.created_at >= date_from)
    if date_to:
        query = query.filter(NotificationDelivery.created_at <= date_to)
    total = query.count()
    rows = (
        query.order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "deliveries": [_serialize_admin_delivery(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/data-sources/health")
def data_source_health(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    snapshot = _latest_completed_snapshot(db)
    return {
        "snapshot": _serialize_snapshot_brief(snapshot),
        "sources": _source_health(db, snapshot),
    }


def _serialize_admin_event(row: MarketEvent) -> dict:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "title": row.title,
        "summary": row.summary,
        "source_provider": row.source_provider,
        "source_url": row.source_url,
        "source_published_at": _iso(row.source_published_at),
        "collected_at": _iso(row.collected_at),
        "data_cutoff_at": _iso(row.data_cutoff_at),
        "assets": row.assets,
        "direction": row.direction,
        "time_horizon": row.time_horizon,
        "confidence": row.confidence,
        "status": row.status,
        "research_snapshot_id": row.research_snapshot_id,
        "created_at": _iso(row.created_at),
    }


@router.get("/research/events")
def admin_research_events(
    event_type: str | None = Query(default=None, max_length=60),
    status: str | None = Query(default=None, max_length=40),
    symbol: str | None = Query(default=None, max_length=40),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    query = db.query(MarketEvent)
    if event_type:
        query = query.filter(MarketEvent.event_type == event_type)
    if status:
        query = query.filter(MarketEvent.status == status)
    if symbol:
        normalized = symbol.upper().strip()
        query = query.filter(
            or_(
                cast(MarketEvent.assets, String).ilike(f'%"{normalized}"%'),
                MarketEvent.id.in_(db.query(AssetImpact.event_id).filter(AssetImpact.symbol == normalized)),
            )
        )
    if date_from:
        query = query.filter(MarketEvent.created_at >= date_from)
    if date_to:
        query = query.filter(MarketEvent.created_at <= date_to)
    total = query.count()
    rows = query.order_by(MarketEvent.created_at.desc(), MarketEvent.id.desc()).offset(offset).limit(limit).all()
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    counts_by_day = (
        db.query(func.date(MarketEvent.created_at).label("day"), MarketEvent.event_type, func.count().label("count"))
        .filter(MarketEvent.created_at >= seven_days_ago)
        .group_by("day", MarketEvent.event_type)
        .order_by("day")
        .all()
    )
    impacts_by_relation = (
        db.query(AssetImpact.relation_type, func.count().label("count"))
        .group_by(AssetImpact.relation_type)
        .all()
    )
    actions_by_status = (
        db.query(ResearchAction.status, func.count().label("count"))
        .group_by(ResearchAction.status)
        .all()
    )
    return {
        "events": [_serialize_admin_event(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "counts_by_day": [{"day": str(day), "event_type": event_type, "count": int(count)} for day, event_type, count in counts_by_day],
        "impacts_by_relation_type": [{"relation_type": relation_type, "count": int(count)} for relation_type, count in impacts_by_relation],
        "actions_by_status": [{"status": status, "count": int(count)} for status, count in actions_by_status],
    }


@router.get("/research/impacts")
def admin_research_impacts(
    symbol: str | None = Query(default=None, max_length=40),
    relation_type: str | None = Query(default=None, max_length=60),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    query = db.query(AssetImpact, MarketEvent.title).join(MarketEvent, MarketEvent.id == AssetImpact.event_id)
    count_query = db.query(AssetImpact)
    if symbol:
        query = query.filter(AssetImpact.symbol == symbol.upper().strip())
        count_query = count_query.filter(AssetImpact.symbol == symbol.upper().strip())
    if relation_type:
        query = query.filter(AssetImpact.relation_type == relation_type)
        count_query = count_query.filter(AssetImpact.relation_type == relation_type)
    if date_from:
        query = query.filter(AssetImpact.created_at >= date_from)
        count_query = count_query.filter(AssetImpact.created_at >= date_from)
    if date_to:
        query = query.filter(AssetImpact.created_at <= date_to)
        count_query = count_query.filter(AssetImpact.created_at <= date_to)
    total = count_query.count()
    rows = query.order_by(AssetImpact.created_at.desc(), AssetImpact.id.desc()).offset(offset).limit(limit).all()
    counts_by_relation = (
        db.query(AssetImpact.relation_type, func.count().label("count"))
        .group_by(AssetImpact.relation_type)
        .all()
    )
    return {
        "impacts": [
            {
                "id": impact.id,
                "event_id": impact.event_id,
                "event_title": title,
                "symbol": impact.symbol,
                "relation_type": impact.relation_type,
                "direction": impact.direction,
                "magnitude": impact.magnitude,
                "confidence": impact.confidence,
                "horizon": impact.horizon,
                "rationale": impact.rationale,
                "created_at": _iso(impact.created_at),
            }
            for impact, title in rows
        ],
        "counts_by_relation_type": [{"relation_type": relation, "count": int(count)} for relation, count in counts_by_relation],
        "user_portfolio_impacts": db.query(UserPortfolioImpact).count(),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/alerts")
def admin_alerts(
    status: str | None = Query(default=None, max_length=40),
    channel: str | None = Query(default=None, max_length=40),
    user_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    query = db.query(Alert)
    if status:
        query = query.filter(Alert.status == status)
    if channel:
        query = query.filter(Alert.channel == channel)
    if user_id:
        query = query.filter(Alert.user_id == user_id)
    total = query.count()
    rows = query.order_by(Alert.created_at.desc(), Alert.id.desc()).offset(offset).limit(limit).all()
    user_ids = sorted({row.user_id for row in rows})
    deliveries_by_pair: dict[tuple[str, str], list[NotificationDelivery]] = {}
    if user_ids:
        deliveries = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.user_id.in_(user_ids))
            .order_by(NotificationDelivery.created_at.desc())
            .limit(500)
            .all()
        )
        for delivery in deliveries:
            deliveries_by_pair.setdefault((delivery.user_id, delivery.channel), []).append(delivery)
    return {
        "alerts": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "asset": row.asset,
                "message": row.message,
                "severity": row.severity,
                "channel": row.channel,
                "status": row.status,
                "sent_at": _iso(row.sent_at),
                "created_at": _iso(row.created_at),
                "deliveries": [
                    _serialize_admin_delivery(delivery)
                    for delivery in deliveries_by_pair.get((row.user_id, row.channel), [])[:3]
                ],
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _serialize_skill_run(row: SkillRun, slug: str | None) -> dict:
    evidence = row.evidence_json if isinstance(row.evidence_json, dict) else {}
    workflow = evidence.get("workflow") if isinstance(evidence.get("workflow"), dict) else None
    workflow_summary = None
    if workflow is not None:
        steps = workflow.get("steps") if isinstance(workflow.get("steps"), list) else []
        workflow_summary = {
            "status": workflow.get("status"),
            "latency_ms": workflow.get("latency_ms"),
            "step_count": len(steps),
            "degraded_steps": workflow.get("degraded_steps") or [],
            "steps": [
                {
                    "id": step.get("id") if isinstance(step, dict) else None,
                    "tool": step.get("tool") if isinstance(step, dict) else None,
                    "status": step.get("status") if isinstance(step, dict) else None,
                    "latency_ms": step.get("latency_ms") if isinstance(step, dict) else None,
                    "error": step.get("error") if isinstance(step, dict) else None,
                }
                for step in steps[:20]
            ],
        }
    return {
        "id": row.id,
        "skill_id": row.skill_id,
        "skill_slug": slug,
        "user_id": row.user_id,
        "status": row.status,
        "trigger_source": row.trigger_source,
        "credits_reserved": row.credits_reserved,
        "credits_used": row.credits_used,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "trace_id": row.trace_id,
        "output_summary": row.output_summary,
        "workflow": workflow_summary,
        "started_at": _iso(row.started_at),
        "completed_at": _iso(row.completed_at),
    }


@router.get("/skill-runs")
def admin_skill_runs(
    slug: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    query = db.query(SkillRun, Skill.slug).outerjoin(Skill, Skill.id == SkillRun.skill_id)
    if slug:
        query = query.filter(Skill.slug == slug)
    if status:
        query = query.filter(SkillRun.status == status)
    total = query.count()
    rows = query.order_by(SkillRun.started_at.desc(), SkillRun.id.desc()).offset(offset).limit(limit).all()
    return {
        "skill_runs": [_serialize_skill_run(run, skill_slug) for run, skill_slug in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stripe/events")
def stripe_events_slash(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    return stripe_events(db=db, user=user)


@router.get("/stripe/summary")
def stripe_summary(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    intents_by_status = (
        db.query(BillingCheckoutIntent.status, func.count().label("count"))
        .group_by(BillingCheckoutIntent.status)
        .all()
    )
    subs_by_status = (
        db.query(Subscription.status, func.count().label("count"))
        .group_by(Subscription.status)
        .all()
    )
    subs_by_plan = (
        db.query(Subscription.plan_name, Subscription.status, func.count().label("count"))
        .group_by(Subscription.plan_name, Subscription.status)
        .all()
    )
    webhook_errors = (
        db.query(StripeWebhookEvent)
        .filter(StripeWebhookEvent.error_message.isnot(None))
        .order_by(StripeWebhookEvent.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "checkout_intents_by_status": [{"status": status, "count": int(count)} for status, count in intents_by_status],
        "subscriptions_by_status": [{"status": status, "count": int(count)} for status, count in subs_by_status],
        "subscriptions_by_plan": [{"plan_name": plan, "status": status, "count": int(count)} for plan, status, count in subs_by_plan],
        "recent_webhook_errors": [
            {
                "id": row.id,
                "stripe_event_id": row.stripe_event_id,
                "event_type": row.event_type,
                "error_message": row.error_message,
                "requires_manual_review": row.requires_manual_review,
                "created_at": _iso(row.created_at),
            }
            for row in webhook_errors
        ],
    }


@router.get("/portfolio-sync")
def admin_portfolio_sync(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    total = db.query(ExchangeConnection).count()
    connections = (
        db.query(ExchangeConnection)
        .order_by(ExchangeConnection.updated_at.desc(), ExchangeConnection.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    sync_runs = (
        db.query(DataSourceSyncRun)
        .order_by(DataSourceSyncRun.started_at.desc())
        .limit(20)
        .all()
    )
    provider_logs = (
        db.query(ProviderSyncLog)
        .order_by(ProviderSyncLog.started_at.desc())
        .limit(20)
        .all()
    )
    return {
        "connections": [_serialize_connection(row) for row in connections],
        "total": total,
        "limit": limit,
        "offset": offset,
        "recent_sync_runs": [serialize_run(row) for row in sync_runs],
        "recent_provider_logs": [serialize_run(row) for row in provider_logs],
    }


@router.get("/backtests")
def admin_backtests(
    status: str | None = Query(default=None, max_length=40),
    engine: str | None = Query(default=None, max_length=60),
    asset: str | None = Query(default=None, max_length=40),
    user_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    query = db.query(BacktestRun)
    if status:
        query = query.filter(BacktestRun.status == status)
    if engine:
        query = query.filter(BacktestRun.engine == engine)
    if asset:
        query = query.filter(BacktestRun.asset == asset.upper().strip())
    if user_id:
        query = query.filter(BacktestRun.user_id == user_id)
    total = query.count()
    rows = query.order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc()).offset(offset).limit(limit).all()

    def _serialize(row: BacktestRun) -> dict:
        duration_seconds = None
        if row.completed_at and row.created_at:
            duration_seconds = round((row.completed_at - row.created_at).total_seconds(), 3)
        error = row.error_json if isinstance(row.error_json, dict) else {}
        return {
            "id": row.id,
            "user_id": row.user_id,
            "status": row.status,
            "engine": row.engine,
            "strategy_id": row.strategy_id,
            "strategy_name": row.strategy_name,
            "asset": row.asset,
            "credits_spent": row.credits_spent,
            "credits_reserved": row.credits_reserved,
            "duration_seconds": duration_seconds,
            "error": error.get("message") or error.get("code") or None,
            "created_at": _iso(row.created_at),
            "completed_at": _iso(row.completed_at),
        }

    return {"backtests": [_serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/trading")
def admin_trading(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    strategies_total = db.query(TradingStrategy).count()
    strategies = (
        db.query(TradingStrategy)
        .order_by(TradingStrategy.updated_at.desc(), TradingStrategy.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    runs = db.query(StrategyRun).order_by(StrategyRun.updated_at.desc()).limit(20).all()
    order_intents = db.query(OrderIntent).order_by(OrderIntent.created_at.desc()).limit(20).all()
    risk_decisions = db.query(RiskDecision).order_by(RiskDecision.created_at.desc()).limit(20).all()
    position_snapshots = db.query(PositionSnapshot).order_by(PositionSnapshot.captured_at.desc()).limit(20).all()
    account_snapshots = db.query(AccountSnapshot).order_by(AccountSnapshot.captured_at.desc()).limit(10).all()
    order_journal = db.query(OrderJournal).order_by(OrderJournal.created_at.desc()).limit(20).all()
    reconciliations = db.query(ReconciliationRecord).order_by(ReconciliationRecord.created_at.desc()).limit(20).all()
    return {
        "strategies": {
            "items": [
                {
                    "id": row.id,
                    "user_id": row.user_id,
                    "name": row.name,
                    "status": row.status,
                    "execution_mode": row.execution_mode,
                    "current_version": row.current_version,
                    "error_code": row.error_code,
                    "error_message": row.error_message,
                    "created_at": _iso(row.created_at),
                    "updated_at": _iso(row.updated_at),
                }
                for row in strategies
            ],
            "total": strategies_total,
            "limit": limit,
            "offset": offset,
        },
        "runs": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "strategy_id": row.strategy_id,
                "strategy_version": row.strategy_version,
                "runtime_run_id": row.runtime_run_id,
                "execution_mode": row.execution_mode,
                "status": row.status,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "started_at": _iso(row.started_at),
                "stopped_at": _iso(row.stopped_at),
                "created_at": _iso(row.created_at),
            }
            for row in runs
        ],
        "order_intents": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "strategy_id": row.strategy_id,
                "account_id": row.account_id,
                "instrument": row.instrument,
                "venue": row.venue,
                "direction": row.direction,
                "quantity": row.quantity,
                "notional": row.notional,
                "order_type": row.order_type,
                "execution_mode": row.execution_mode,
                "status": row.status,
                "approval_status": row.approval_status,
                "error_message": row.error_message,
                "created_at": _iso(row.created_at),
                "expires_at": _iso(row.expires_at),
            }
            for row in order_intents
        ],
        "risk_decisions": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "strategy_id": row.strategy_id,
                "order_intent_id": row.order_intent_id,
                "decision": row.decision,
                "reasons": row.reasons,
                "created_at": _iso(row.created_at),
            }
            for row in risk_decisions
        ],
        "position_snapshots": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "account_id": row.account_id,
                "strategy_id": row.strategy_id,
                "instrument": row.instrument,
                "quantity": row.quantity,
                "side": row.side,
                "average_price": row.average_price,
                "mark_price": row.mark_price,
                "unrealized_pnl": row.unrealized_pnl,
                "realized_pnl": row.realized_pnl,
                "leverage": row.leverage,
                "captured_at": _iso(row.captured_at),
            }
            for row in position_snapshots
        ],
        "account_snapshots": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "account_id": row.account_id,
                "balance": row.balance,
                "equity": row.equity,
                "available_margin": row.available_margin,
                "daily_pnl": row.daily_pnl,
                "drawdown": row.drawdown,
                "exposure": row.exposure,
                "stale": row.stale,
                "captured_at": _iso(row.captured_at),
            }
            for row in account_snapshots
        ],
        "order_journal": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "account_id": row.account_id,
                "client_order_id": row.client_order_id,
                "exchange_order_id": row.exchange_order_id,
                "state": row.state,
                "instrument": row.instrument,
                "side": row.side,
                "quantity": row.quantity,
                "filled_quantity": row.filled_quantity,
                "average_price": row.average_price,
                "error_message": row.error_message,
                "created_at": _iso(row.created_at),
            }
            for row in order_journal
        ],
        "reconciliations": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "account_id": row.account_id,
                "strategy_id": row.strategy_id,
                "status": row.status,
                "differences": row.differences_json,
                "error_message": row.error_message,
                "created_at": _iso(row.created_at),
                "completed_at": _iso(row.completed_at),
            }
            for row in reconciliations
        ],
    }


@router.get("/custody")
def admin_custody(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    accounts = db.query(CustodyAccount).order_by(CustodyAccount.created_at.desc()).limit(50).all()
    sub_total = db.query(CustodySubAccount).count()
    sub_accounts = (
        db.query(CustodySubAccount)
        .order_by(CustodySubAccount.updated_at.desc(), CustodySubAccount.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    ledger = db.query(CustodyLedgerEntry).order_by(CustodyLedgerEntry.created_at.desc()).limit(30).all()
    deposits_by_status = (
        db.query(CustodyDeposit.status, func.count().label("count"))
        .group_by(CustodyDeposit.status)
        .all()
    )
    withdrawals_by_status = (
        db.query(CustodyWithdrawal.status, func.count().label("count"))
        .group_by(CustodyWithdrawal.status)
        .all()
    )
    recent_deposits = db.query(CustodyDeposit).order_by(CustodyDeposit.created_at.desc()).limit(10).all()
    recent_withdrawals = db.query(CustodyWithdrawal).order_by(CustodyWithdrawal.created_at.desc()).limit(10).all()
    reconciliations = db.query(CustodyReconciliation).order_by(CustodyReconciliation.created_at.desc()).limit(10).all()
    return {
        "accounts": [
            {
                "id": row.id,
                "venue": row.venue,
                "environment": row.environment,
                "status": row.status,
                "deposit_address": row.deposit_address,
                "provider_ref": row.provider_ref,
                "created_at": _iso(row.created_at),
            }
            for row in accounts
        ],
        "sub_accounts": {
            "items": [
                {
                    "id": row.id,
                    "custody_account_id": row.custody_account_id,
                    "user_id": row.user_id,
                    "asset": row.asset,
                    "available": _num(row.available),
                    "frozen": _num(row.frozen),
                    "created_at": _iso(row.created_at),
                    "updated_at": _iso(row.updated_at),
                }
                for row in sub_accounts
            ],
            "total": sub_total,
            "limit": limit,
            "offset": offset,
        },
        "recent_ledger": [
            {
                "id": row.id,
                "sub_account_id": row.sub_account_id,
                "entry_type": row.entry_type,
                "amount": _num(row.amount),
                "available_after": _num(row.available_after),
                "frozen_after": _num(row.frozen_after),
                "ref_type": row.ref_type,
                "ref_id": row.ref_id,
                "created_at": _iso(row.created_at),
            }
            for row in ledger
        ],
        "deposits_by_status": [{"status": status, "count": int(count)} for status, count in deposits_by_status],
        "withdrawals_by_status": [{"status": status, "count": int(count)} for status, count in withdrawals_by_status],
        "recent_deposits": [
            {
                "id": row.id,
                "sub_account_id": row.sub_account_id,
                "asset": row.asset,
                "amount": _num(row.amount),
                "tx_ref": row.tx_ref,
                "confirmations": row.confirmations,
                "status": row.status,
                "created_at": _iso(row.created_at),
                "confirmed_at": _iso(row.confirmed_at),
            }
            for row in recent_deposits
        ],
        "recent_withdrawals": [
            {
                "id": row.id,
                "sub_account_id": row.sub_account_id,
                "asset": row.asset,
                "amount": _num(row.amount),
                "address": row.address,
                "status": row.status,
                "tx_ref": row.tx_ref,
                "error": row.error,
                "created_at": _iso(row.created_at),
            }
            for row in recent_withdrawals
        ],
        "reconciliations": [
            {
                "id": row.id,
                "custody_account_id": row.custody_account_id,
                "asset": row.asset,
                "local_available": _num(row.local_available),
                "local_frozen": _num(row.local_frozen),
                "external_balance": _num(row.external_balance),
                "difference": _num(row.difference),
                "status": row.status,
                "created_at": _iso(row.created_at),
            }
            for row in reconciliations
        ],
    }


def _celery_worker_payload() -> dict:
    """Introspect the Celery cluster; degrade to an explicit unavailable state."""
    try:
        from packages.workers.celery_app import celery_app
    except Exception as exc:
        return {"status": "unavailable", "reason": f"celery_import_failed: {exc}", "workers": {}}
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        active = inspector.active() or {}
        scheduled = inspector.scheduled() or {}
        reserved = inspector.reserved() or {}
    except Exception as exc:
        return {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"[:300], "workers": {}}
    names = sorted(set(active) | set(scheduled) | set(reserved))
    if not names:
        return {"status": "unavailable", "reason": "no_workers_online", "workers": {}}
    return {
        "status": "ok",
        "reason": None,
        "workers": {
            name: {
                "active": len(active.get(name) or []),
                "scheduled": len(scheduled.get(name) or []),
                "reserved": len(reserved.get(name) or []),
                "active_tasks": [str(task.get("name")) for task in (active.get(name) or []) if isinstance(task, dict)][:20],
            }
            for name in names
        },
    }


def _celery_queue_lengths() -> dict:
    try:
        from apps.api.redis_client import get_redis

        client = get_redis()
        queue_names = {"celery"}
        try:
            from packages.workers.celery_app import celery_app

            inspector = celery_app.control.inspect(timeout=1.0)
            for _, queues in (inspector.active_queues() or {}).items():
                for queue in queues or []:
                    if isinstance(queue, dict) and queue.get("name"):
                        queue_names.add(str(queue["name"]))
        except Exception:
            pass
        lengths: dict[str, int | None] = {}
        for name in sorted(queue_names):
            try:
                lengths[name] = int(client.llen(name))
            except Exception:
                lengths[name] = None
        return lengths
    except Exception:
        return {}


@router.get("/workers")
def admin_workers(db: Session = Depends(get_db), user: User = Depends(admin_user)) -> dict:
    recent_failures = (
        db.query(DataSourceSyncRun)
        .filter(DataSourceSyncRun.status == "FAILED")
        .order_by(DataSourceSyncRun.started_at.desc())
        .limit(10)
        .all()
    )
    return {
        "celery": _celery_worker_payload(),
        "queues": _celery_queue_lengths(),
        "recent_sync_failures": [serialize_run(row) for row in recent_failures],
    }


# =============================================================================
# LIVE Trading Control Plane admin surface.
# Only admins can approve users, create broker connections or move kill
# switches. Ordinary admin web pages do NOT reach these endpoints directly:
# every LIVE order still flows through the Trading Control Plane.
# =============================================================================


class LiveApprovalRequest(BaseModel):
    user_id: str
    approve: bool = True
    max_total_notional: str = Field(default="0", pattern=r"^\d+(\.\d+)?$")
    notes: str = Field(default="", max_length=2000)


class AdminKillSwitchRequest(BaseModel):
    scope: str = Field(pattern="^(global|user|mandate|connection)$")
    scope_id: str | None = None
    active: bool = True
    reason: str = Field(min_length=1, max_length=2000)


class AdminBrokerConnectionRequest(BaseModel):
    user_id: str
    provider: str = Field(min_length=1, max_length=64)
    account_label: str = Field(min_length=1, max_length=128)
    environment: str = Field(default="paper", pattern="^(paper|testnet|production)$")
    credentials: dict = Field(default_factory=dict)


@router.post("/trading/live-approvals")
def admin_live_approval(
    payload: LiveApprovalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from packages.database.models import LiveUserApproval, utcnow as model_utcnow

    target = db.query(User).filter_by(id=payload.user_id).one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    row = db.query(LiveUserApproval).filter_by(user_id=payload.user_id).one_or_none()
    if not row:
        row = LiveUserApproval(user_id=payload.user_id)
        db.add(row)
    row.status = "approved" if payload.approve else "rejected"
    row.max_total_notional = payload.max_total_notional
    row.reviewed_by = user.id
    row.reviewed_at = model_utcnow()
    row.notes = payload.notes or None
    if not payload.approve:
        row.revoked_at = model_utcnow()
    db.commit()
    db.refresh(row)
    return {
        "approval": {
            "id": row.id,
            "user_id": row.user_id,
            "status": row.status,
            "max_total_notional": str(row.max_total_notional),
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        }
    }


@router.post("/trading/kill-switch")
def admin_kill_switch(
    payload: AdminKillSwitchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from packages.live_trading import kill_switch as kill_switch_service
    from packages.live_trading.audit import new_trace_id
    from packages.database.models import TradingMandate

    trace_id = new_trace_id()
    if payload.active:
        row = kill_switch_service.engage(
            db,
            scope=payload.scope,
            scope_id=payload.scope_id,
            reason=payload.reason,
            triggered_by="admin",
            trace_id=trace_id,
        )
        if payload.scope == "mandate" and payload.scope_id:
            mandate = db.query(TradingMandate).filter_by(id=payload.scope_id).one_or_none()
            if mandate:
                mandate.kill_switch_state = "active"
                mandate.paused = True
                mandate.pause_reason = f"admin kill switch: {payload.reason[:500]}"
    else:
        released = kill_switch_service.release(
            db,
            scope=payload.scope,
            scope_id=payload.scope_id,
            resolved_by=user.id,
            trace_id=trace_id,
        )
        if not released:
            raise HTTPException(status_code=404, detail="No active kill switch in scope")
        if payload.scope == "mandate" and payload.scope_id:
            mandate = db.query(TradingMandate).filter_by(id=payload.scope_id).one_or_none()
            if mandate and mandate.kill_switch_state == "active":
                mandate.kill_switch_state = "inactive"
    db.commit()
    return {"trace_id": trace_id, "active": payload.active, "scope": payload.scope}


@router.post("/trading/connections")
def admin_create_broker_connection(
    payload: AdminBrokerConnectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from packages.database.models import BrokerConnection
    from packages.live_trading.secret_store import encrypt_secrets

    target = db.query(User).filter_by(id=payload.user_id).one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    existing = (
        db.query(BrokerConnection)
        .filter_by(
            user_id=payload.user_id,
            provider=payload.provider,
            account_label=payload.account_label,
        )
        .one_or_none()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Connection label already exists")
    row = BrokerConnection(
        user_id=payload.user_id,
        provider=payload.provider,
        account_label=payload.account_label,
        encrypted_credentials_ref=encrypt_secrets(payload.credentials)
        if payload.credentials
        else None,
        permissions_json={
            "spot": True,
            "margin": False,
            "futures": False,
            "options": False,
            "shorting": False,
            "withdraw": False,
            "transfer": False,
        },
        environment=payload.environment,
        status="DISCONNECTED",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "connection": {
            "id": row.id,
            "user_id": row.user_id,
            "provider": row.provider,
            "account_label": row.account_label,
            "environment": row.environment,
            "status": row.status,
            "has_credentials": bool(row.encrypted_credentials_ref),
        }
    }


@router.get("/trading/ledger")
def admin_ledger_entries(
    user_id: str | None = None,
    account_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from packages.database.models import LedgerEntry

    query = db.query(LedgerEntry)
    if user_id:
        query = query.filter_by(user_id=user_id)
    if account_id:
        query = query.filter_by(account_id=account_id)
    rows = query.order_by(LedgerEntry.created_at.desc()).limit(limit).all()
    return {
        "entries": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "account_id": row.account_id,
                "mandate_id": row.mandate_id,
                "entry_type": row.entry_type,
                "ref_type": row.ref_type,
                "ref_id": row.ref_id,
                "symbol": row.symbol,
                "quantity": str(row.quantity) if row.quantity is not None else None,
                "price": str(row.price) if row.price is not None else None,
                "amount": str(row.amount),
                "currency": row.currency,
                "balance_after": str(row.balance_after) if row.balance_after is not None else None,
                "trace_id": row.trace_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/trading/reconciliations")
def admin_reconciliations(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> dict:
    from packages.database.models import TradingReconciliation

    rows = (
        db.query(TradingReconciliation)
        .order_by(TradingReconciliation.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "reconciliations": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "account_id": row.account_id,
                "mandate_id": row.mandate_id,
                "status": row.status,
                "exchange_balance": row.exchange_balance_json,
                "ledger_balance": row.ledger_balance_json,
                "nav": row.nav_json,
                "differences": row.differences_json,
                "actions": row.actions_json,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
