from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db
from apps.api.services.credit_service import InsufficientCreditsError, quote_task, refund_task, reserve_task, settle_task
from apps.api.services.portfolio_service import autopilot_view, connect_hyperliquid, connect_ibkr_token, connect_plaid, disconnect_account, plaid_link_token, portfolio_view, run_autopilot_review, sync_account, update_autopilot
from packages.database.models import MobileOAuthSession, TradingAccount, User, UserPreference, utcnow


router = APIRouter(prefix="/portfolio", tags=["portfolio"])
MOBILE_IBKR_TTL_SECONDS = 600


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


class MobileIBKRStartRequest(BaseModel):
    redirect_uri: str = Field(min_length=8, max_length=512)


class MobileIBKRCompleteRequest(BaseModel):
    code: str = Field(min_length=32, max_length=512)


def _mobile_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _mobile_expired(value) -> bool:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware < utcnow()


def _mobile_redirect(uri: str, **values: str) -> str:
    parts = urlsplit(uri)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(values)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


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


@router.post("/ibkr/mobile/start")
def ibkr_mobile_start(
    payload: MobileIBKRStartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    if payload.redirect_uri not in set(settings.mobile_portfolio_redirect_uris):
        raise HTTPException(status_code=400, detail={"code": "MOBILE_REDIRECT_URI_INVALID"})
    if not all((settings.ibkr_oauth_authorize_url, settings.ibkr_oauth_token_url, settings.ibkr_client_id, settings.ibkr_client_secret)):
        raise HTTPException(status_code=503, detail={"code": "IBKR_OAUTH_NOT_CONFIGURED"})
    state = secrets.token_urlsafe(48)
    row = MobileOAuthSession(
        provider="ibkr",
        state=state,
        client_state=secrets.token_urlsafe(32),
        client_nonce=secrets.token_urlsafe(32),
        provider_nonce=secrets.token_urlsafe(32),
        provider_code_verifier="server-side",
        code_challenge="server-side",
        redirect_uri=payload.redirect_uri,
        user_id=user.id,
        expires_at=utcnow() + timedelta(seconds=MOBILE_IBKR_TTL_SECONDS),
    )
    db.add(row)
    db.commit()
    query = urlencode({
        "client_id": settings.ibkr_client_id,
        "redirect_uri": settings.mobile_ibkr_oauth_redirect_uri,
        "response_type": "code",
        "scope": "portfolio",
        "state": state,
    })
    return {"authorize_url": f"{settings.ibkr_oauth_authorize_url}?{query}", "expires_at": row.expires_at.isoformat()}


@router.get("/ibkr/mobile/callback")
def ibkr_mobile_callback(
    state: str,
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    row = db.query(MobileOAuthSession).filter_by(state=state, provider="ibkr").one_or_none()
    if not row or row.consumed_at or row.exchange_code_hash or _mobile_expired(row.expires_at) or not row.user_id:
        raise HTTPException(status_code=400, detail={"code": "MOBILE_IBKR_SESSION_INVALID"})
    if error or not code:
        row.consumed_at = utcnow()
        db.commit()
        return RedirectResponse(_mobile_redirect(row.redirect_uri, error="oauth_canceled"), status_code=302)
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(status_code=400, detail={"code": "MOBILE_IBKR_USER_MISSING"})
    try:
        response = requests.post(settings.ibkr_oauth_token_url, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.mobile_ibkr_oauth_redirect_uri,
            "client_id": settings.ibkr_client_id,
            "client_secret": settings.ibkr_client_secret,
        }, timeout=20)
        response.raise_for_status()
        account = connect_ibkr_token(db, user, response.json())
        sync_account(db, user, account)
    except Exception:
        db.rollback()
        row = db.query(MobileOAuthSession).filter_by(state=state, provider="ibkr").one()
        row.consumed_at = utcnow()
        db.commit()
        return RedirectResponse(_mobile_redirect(row.redirect_uri, error="ibkr_connection_failed"), status_code=302)
    exchange_code = secrets.token_urlsafe(48)
    row = db.query(MobileOAuthSession).filter_by(state=state, provider="ibkr").one()
    row.exchange_code_hash = _mobile_hash(exchange_code)
    row.provider_code_verifier = "consumed"
    db.commit()
    return RedirectResponse(_mobile_redirect(row.redirect_uri, code=exchange_code), status_code=302)


@router.post("/ibkr/mobile/complete")
def ibkr_mobile_complete(
    payload: MobileIBKRCompleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = db.query(MobileOAuthSession).filter_by(exchange_code_hash=_mobile_hash(payload.code), provider="ibkr").one_or_none()
    if not row or row.consumed_at or _mobile_expired(row.expires_at) or row.user_id != user.id:
        raise HTTPException(status_code=400, detail={"code": "MOBILE_IBKR_EXCHANGE_INVALID"})
    row.consumed_at = utcnow()
    row.exchange_code_hash = None
    db.commit()
    return portfolio_view(db, user)


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
