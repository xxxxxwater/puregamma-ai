from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db
from apps.api.services.credit_service import InsufficientCreditsError, quote_task, refund_task, reserve_task, settle_task
from apps.api.services.portfolio_service import autopilot_view, connect_hyperliquid, connect_ibkr_token, connect_plaid, disconnect_account, plaid_link_token, portfolio_view, run_autopilot_review, sync_account, update_autopilot
from packages.database.models import TradingAccount, User, UserPreference


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _ibkr_state(user_id: str) -> str:
    timestamp = str(int(time.time()))
    message = f"{user_id}.{timestamp}"
    signature = hmac.new(get_settings().jwt_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"{message}.{signature}"


def _verify_ibkr_state(state: str, user_id: str) -> None:
    try:
        state_user, timestamp, signature = state.split(".", 2)
        message = f"{state_user}.{timestamp}"
        expected = hmac.new(get_settings().jwt_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        if state_user != user_id or int(time.time()) - int(timestamp) > 600 or not hmac.compare_digest(signature, expected):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired IBKR OAuth state") from exc


class PlaidExchangeRequest(BaseModel):
    public_token: str
    institution_name: str = "Plaid Investments"


class HyperliquidRequest(BaseModel):
    address: str


class AutopilotRequest(BaseModel):
    enabled: bool | None = None
    cadence: str | None = None
    auto_sync: bool | None = None
    risk_alerts: bool | None = None
    long_gamma_watch: bool | None = None
    delivery: str | None = None


class PortfolioPrivacyRequest(BaseModel):
    include_portfolio_in_ai: bool


@router.get("")
def get_portfolio(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return portfolio_view(db, user)


@router.put("/ai-context")
def update_ai_context(payload: PortfolioPrivacyRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    preference = db.query(UserPreference).filter_by(user_id=user.id).one_or_none()
    if not preference:
        preference = UserPreference(user_id=user.id)
        db.add(preference)
    preference.include_portfolio_in_ai = payload.include_portfolio_in_ai
    db.commit()
    return {"include_portfolio_in_ai": preference.include_portfolio_in_ai}


@router.get("/autopilot")
def get_autopilot(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return autopilot_view(db, user)


@router.put("/autopilot")
def put_autopilot(payload: AutopilotRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return update_autopilot(db, user, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/autopilot/run")
def run_review(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    quote = quote_task(task_type="portfolio_monitor", async_execution=True)
    reservation = None
    try:
        reservation = reserve_task(
            db,
            user.id,
            quote,
            f"portfolio-review:{user.id}:{idempotency_key or uuid.uuid4()}",
            {"source": "user_initiated"},
        )
        db.commit()
        result = run_autopilot_review(db, user)
        settle_task(db, user.id, reservation, quote.credits, metadata={"reviewed_at": result["last_review"]})
        db.commit()
        return result
    except InsufficientCreditsError as exc:
        db.rollback()
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        if reservation:
            refund_task(db, user.id, reservation, "PORTFOLIO_REVIEW_REJECTED")
            db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        if reservation:
            refund_task(db, user.id, reservation, "PORTFOLIO_REVIEW_FAILED")
            db.commit()
        raise


@router.post("/plaid/link-token")
def create_plaid_link_token(user: User = Depends(get_current_user)) -> dict:
    try:
        return {"link_token": plaid_link_token(user)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/plaid/exchange")
def exchange_plaid(payload: PlaidExchangeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        account = connect_plaid(db, user, payload.public_token, payload.institution_name)
        sync_account(db, user, account)
        return portfolio_view(db, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/hyperliquid/connect")
def add_hyperliquid(payload: HyperliquidRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        account = connect_hyperliquid(db, user, payload.address)
        sync_account(db, user, account)
        return portfolio_view(db, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/ibkr/authorize")
def ibkr_authorize(user: User = Depends(get_current_user)) -> dict:
    settings = get_settings()
    if not settings.ibkr_oauth_authorize_url or not settings.ibkr_client_id:
        raise HTTPException(status_code=503, detail="IBKR OAuth is not configured")
    query = urlencode({"client_id": settings.ibkr_client_id, "redirect_uri": settings.ibkr_redirect_uri, "response_type": "code", "scope": "portfolio", "state": _ibkr_state(user.id)})
    return {"authorize_url": f"{settings.ibkr_oauth_authorize_url}?{query}"}


@router.post("/ibkr/exchange")
def ibkr_exchange(code: str, state: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    settings = get_settings()
    _verify_ibkr_state(state, user.id)
    if not settings.ibkr_oauth_token_url or not settings.ibkr_client_secret:
        raise HTTPException(status_code=503, detail="IBKR OAuth token exchange is not configured")
    response = requests.post(settings.ibkr_oauth_token_url, data={"grant_type": "authorization_code", "code": code, "redirect_uri": settings.ibkr_redirect_uri, "client_id": settings.ibkr_client_id, "client_secret": settings.ibkr_client_secret}, timeout=20)
    try:
        response.raise_for_status()
        account = connect_ibkr_token(db, user, response.json())
        sync_account(db, user, account)
        return portfolio_view(db, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/sync")
def sync_connected_account(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    account = db.query(TradingAccount).filter_by(id=account_id, user_id=user.id, account_type="READ_ONLY").one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Portfolio account not found")
    try:
        sync_account(db, user, account)
        return portfolio_view(db, user)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/accounts/{account_id}")
def disconnect_connected_account(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    account = db.query(TradingAccount).filter_by(id=account_id, user_id=user.id, account_type="READ_ONLY").one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Portfolio account not found")
    disconnect_account(db, user, account)
    return portfolio_view(db, user)
