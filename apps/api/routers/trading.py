from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db, require_admin
from apps.api.services.trading_service import (
    TradingServiceError,
    account_performance,
    cancel_order,
    confirm_order,
    list_accounts,
    list_orders,
    list_positions,
    preview_order,
    reconcile_account,
    serialize_order,
    serialize_order_intent,
)
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.runtime_sync_service import sync_runtime_account
from packages.database.models import StrategyRun, TradingAccount, User
from packages.trading.policies.safety import LiveExecutionDenied
from packages.trading.runtime_client import NautilusRuntimeClient, RuntimeUnavailable


router = APIRouter(prefix="/trading", tags=["trading"])


class OrderPreviewRequest(BaseModel):
    payload: dict
    conversation_id: str | None = None


class OrderConfirmRequest(BaseModel):
    order_intent_id: str
    confirmation: str = Field(min_length=16, max_length=500)


class ReconcileRequest(BaseModel):
    account_id: str


class OrderCancelRequest(BaseModel):
    client_order_id: str


class KillSwitchRequest(BaseModel):
    enabled: bool


class RuntimeSyncRequest(BaseModel):
    account_id: str


def control_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RuntimeUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, InsufficientCreditsError):
        return HTTPException(status_code=402, detail=str(exc))
    if isinstance(exc, (TradingServiceError, LiveExecutionDenied, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Trading control failed")


@router.get("/accounts")
def accounts(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return {"accounts": list_accounts(db, user.id)}


@router.get("/positions")
def positions(
    account_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return {"positions": list_positions(db, user.id, account_id)}


@router.get("/performance")
def performance(
    account_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return account_performance(db, user.id, account_id)
    except Exception as exc:
        raise control_error(exc) from exc


@router.get("/orders")
def orders(
    account_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return {"orders": list_orders(db, user.id, account_id)}


@router.post("/orders/preview")
def order_preview(
    payload: OrderPreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        intent, confirmation = preview_order(
            db, user.id, payload.payload, conversation_id=payload.conversation_id
        )
        return {"intent": serialize_order_intent(intent, confirmation)}
    except Exception as exc:
        raise control_error(exc) from exc


@router.post("/orders/confirm")
def order_confirm(
    payload: OrderConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return {
            "order": serialize_order(
                confirm_order(
                    db, user.id, payload.order_intent_id, payload.confirmation
                )
            )
        }
    except Exception as exc:
        raise control_error(exc) from exc


@router.post("/orders/cancel")
def order_cancel(
    payload: OrderCancelRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return {
            "order": serialize_order(cancel_order(db, user.id, payload.client_order_id))
        }
    except Exception as exc:
        raise control_error(exc) from exc


@router.post("/reconcile")
def reconcile(
    payload: ReconcileRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        row = reconcile_account(db, user.id, payload.account_id)
        return {
            "reconciliation": {
                "id": row.id,
                "account_id": row.account_id,
                "status": row.status,
                "differences": row.differences_json,
                "actions": row.actions_json,
                "completed_at": row.completed_at.isoformat()
                if row.completed_at
                else None,
            }
        }
    except Exception as exc:
        raise control_error(exc) from exc


@router.get("/runtime/health")
def runtime_health(user: User = Depends(get_current_user)) -> dict:
    try:
        return NautilusRuntimeClient().health()
    except Exception as exc:
        raise control_error(exc) from exc


@router.get("/runtime/market")
def runtime_market(
    symbols: list[str] | None = None,
    refresh: bool = False,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return NautilusRuntimeClient().market_quotes(symbols, refresh=refresh)
    except Exception as exc:
        raise control_error(exc) from exc


@router.get("/runtime/events")
def runtime_events(
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        result = NautilusRuntimeClient().events(limit=max(1, min(limit, 500)))
        owned_runs = {
            row.runtime_run_id
            for row in db.query(StrategyRun.runtime_run_id)
            .filter(StrategyRun.user_id == user.id)
            .all()
        }
        result["events"] = [
            event
            for event in result.get("events", [])
            if event.get("aggregate_id") in owned_runs
            or event.get("payload", {}).get("run_id") in owned_runs
        ]
        return result
    except Exception as exc:
        raise control_error(exc) from exc


@router.post("/runtime/sync")
def runtime_sync(
    payload: RuntimeSyncRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        account = (
            db.query(TradingAccount)
            .filter_by(id=payload.account_id, user_id=user.id)
            .one_or_none()
        )
        if not account:
            raise LookupError("Trading account not found")
        return {"sync": sync_runtime_account(db, account)}
    except Exception as exc:
        raise control_error(exc) from exc


@router.post("/runtime/kill-switch")
def kill_switch(
    payload: KillSwitchRequest, user: User = Depends(get_current_user)
) -> dict:
    require_admin(user)
    try:
        return NautilusRuntimeClient().command(
            "kill_switch",
            f"kill-switch:{payload.enabled}",
            {"enabled": payload.enabled},
        )
    except Exception as exc:
        raise control_error(exc) from exc
