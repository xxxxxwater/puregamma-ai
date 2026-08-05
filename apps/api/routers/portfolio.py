from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from redis import Redis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db
from apps.api.services.cex_connection_service import cex_connection_status, connect_cex
from apps.api.services.credit_service import InsufficientCreditsError, quote_task, refund_task, reserve_task, settle_task
from apps.api.services.portfolio_service import PlaidDataPending, PlaidRefreshRateLimited, PlaidRefreshUnsupported, PlaidWebhookVerificationError, PortfolioAccessError, autopilot_view, connect_evm_wallet, connect_hyperliquid, connect_ibkr_token, connect_plaid, disconnect_account, plaid_investment_transactions, plaid_link_token, portfolio_view, process_plaid_webhook, request_plaid_investments_refresh, run_autopilot_review, sync_account, update_autopilot, verify_plaid_webhook
from packages.data.cex_private import CexPermissionDenied
from apps.api.services.skill_service import begin_module_skill_invocation, finish_module_skill_invocation
from packages.database.models import MobileOAuthSession, TradingAccount, User, UserPreference, utcnow
from packages.skills.registry import SkillResolutionError


def _portfolio_access_http(exc: PermissionError) -> HTTPException:
    if isinstance(exc, PortfolioAccessError):
        return HTTPException(status_code=403, detail={"code": exc.code, **exc.context})
    return HTTPException(status_code=403, detail={"code": str(exc)})


router = APIRouter(prefix="/portfolio", tags=["portfolio"])
MOBILE_IBKR_TTL_SECONDS = 600
EVM_CHALLENGE_TTL_SECONDS = 300
logger = logging.getLogger(__name__)


def _enqueue_plaid_history_sync(account_id: str) -> None:
    """Keep Link and webhook handlers fast; the worker fetches up to 24 months."""
    from packages.workers.tasks import sync_plaid_investments_account

    sync_plaid_investments_account.delay(account_id)


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


class CexConnectRequest(BaseModel):
    venue: str = Field(min_length=1, max_length=32)
    api_key: str = Field(min_length=1, max_length=256)
    api_secret: str = Field(min_length=1, max_length=512)
    passphrase: str | None = Field(default=None, max_length=256)
    environment: str = Field(default="production", max_length=32)


class EVMChallengeRequest(BaseModel):
    address: str = Field(min_length=42, max_length=42)
    chain_id: int = Field(gt=0)


class EVMConnectRequest(EVMChallengeRequest):
    challenge_token: str = Field(min_length=32, max_length=2048)
    message: str = Field(min_length=32, max_length=4096)
    signature: str = Field(min_length=132, max_length=132)


class AutopilotRequest(BaseModel):
    enabled: bool | None = None
    cadence: str | None = None
    auto_sync: bool | None = None
    risk_alerts: bool | None = None
    long_gamma_watch: bool | None = None
    delivery: str | None = None
    skill_refs: list[dict] | None = Field(default=None, max_length=8)


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


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _evm_challenge_key(token: str) -> str:
    return f"portfolio:evm-challenge:{hashlib.sha256(token.encode()).hexdigest()}"


def _evm_challenge(user: User, address: str, chain_id: int) -> tuple[str, str]:
    normalized = address.strip().lower()
    if not normalized.startswith("0x") or len(normalized) != 42 or any(ch not in "0123456789abcdef" for ch in normalized[2:]):
        raise ValueError("Invalid EVM wallet address")
    issued_at = int(time.time())
    nonce = secrets.token_hex(16)
    payload = {
        "user_id": user.id,
        "address": normalized,
        "chain_id": chain_id,
        "nonce": nonce,
        "issued_at": issued_at,
    }
    encoded = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(get_settings().jwt_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    token = f"{encoded}.{signature}"
    issued = datetime.fromtimestamp(issued_at, timezone.utc).isoformat().replace("+00:00", "Z")
    message = (
        "app.puregamma.ai wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        "Verify this wallet for read-only multi-chain portfolio tracking. No transaction or token approval will be requested.\n\n"
        "URI: https://app.puregamma.ai/portfolio\n"
        "Version: 1\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued}"
    )
    return message, token


def _verify_evm_challenge(payload: EVMConnectRequest, user: User) -> None:
    try:
        encoded, signature = payload.challenge_token.split(".", 1)
        expected_signature = hmac.new(get_settings().jwt_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError
        challenge = json.loads(_b64url_decode(encoded))
        if challenge.get("user_id") != user.id:
            raise ValueError
        if challenge.get("address") != payload.address.lower() or int(challenge.get("chain_id")) != payload.chain_id:
            raise ValueError
        if int(time.time()) - int(challenge.get("issued_at")) > EVM_CHALLENGE_TTL_SECONDS:
            raise ValueError
        expected_message, _ = _evm_challenge_from_payload(payload.address, challenge)
        if not hmac.compare_digest(payload.message, expected_message):
            raise ValueError
        recovered = Account.recover_message(encode_defunct(text=payload.message), signature=payload.signature)
        if recovered.lower() != payload.address.lower():
            raise ValueError
        redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
        if redis.getdel(_evm_challenge_key(payload.challenge_token)) != user.id:
            raise ValueError
    except Exception as exc:
        raise ValueError("Invalid or expired wallet signature") from exc


def _evm_challenge_from_payload(address: str, challenge: dict) -> tuple[str, str]:
    issued = datetime.fromtimestamp(int(challenge["issued_at"]), timezone.utc).isoformat().replace("+00:00", "Z")
    message = (
        "app.puregamma.ai wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        "Verify this wallet for read-only multi-chain portfolio tracking. No transaction or token approval will be requested.\n\n"
        "URI: https://app.puregamma.ai/portfolio\n"
        "Version: 1\n"
        f"Chain ID: {int(challenge['chain_id'])}\n"
        f"Nonce: {challenge['nonce']}\n"
        f"Issued At: {issued}"
    )
    return message, ""


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
    skill_invocation_id = None
    try:
        config = autopilot_view(db, user)["config"]
        skill_invocation_id, _ = begin_module_skill_invocation(
            db,
            user,
            config.get("skill_refs", []),
            trigger_source="autopilot",
            input_payload={"query": "Run the configured portfolio Autopilot review", "portfolio_user_id": user.id, "config": config},
            estimated_credits=quote.credits,
            allow_autopilot=True,
            required_tool="get_account_snapshot",
            invocation_id=f"portfolio-skill:{user.id}:{idempotency_key}" if idempotency_key else None,
        )
        db.commit()
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
        finish_module_skill_invocation(db, skill_invocation_id, status="completed", credits_used=quote.credits, output_summary="Portfolio Autopilot review", evidence={"reviewed_at": result["last_review"], "account_count": result["account_count"]})
        db.commit()
        return result
    except SkillResolutionError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except InsufficientCreditsError as exc:
        db.rollback()
        if skill_invocation_id:
            finish_module_skill_invocation(db, skill_invocation_id, status="failed", credits_used=0, error_code="AUTOPILOT_CREDITS_REJECTED")
            db.commit()
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        if reservation:
            refund_task(db, user.id, reservation, "PORTFOLIO_REVIEW_REJECTED")
        if skill_invocation_id:
            finish_module_skill_invocation(db, skill_invocation_id, status="failed", credits_used=0, error_code="AUTOPILOT_REJECTED")
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        if reservation:
            refund_task(db, user.id, reservation, "PORTFOLIO_REVIEW_FAILED")
        if skill_invocation_id:
            finish_module_skill_invocation(db, skill_invocation_id, status="failed", credits_used=0, error_code="AUTOPILOT_FAILED")
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
        # Holdings establish the initial NAV promptly. Investments transaction
        # history can take one to two minutes after Link, so it is queued.
        sync_account(db, user, account, include_transactions=False)
        try:
            _enqueue_plaid_history_sync(account.id)
        except Exception:
            logger.exception("plaid_history_dispatch_failed account_id=%s", account.id)
            # Redis/Celery is normally mandatory in production. The inline
            # fallback keeps a successful Link exchange usable if it is down.
            try:
                sync_account(db, user, account, include_transactions=True)
            except PlaidDataPending:
                pass
        result = portfolio_view(db, user)
        result["plaid_history_sync"] = "pending"
        return result
    except PermissionError as exc:
        raise _portfolio_access_http(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/cex/connect")
def add_cex_connection(payload: CexConnectRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Connect a Binance/OKX/Bybit read-only API key pair.

    The plaintext secret is used only for the signed permission probe and is
    stored solely as Fernet ciphertext; this response never echoes it.
    """
    try:
        account = connect_cex(db, user, payload.venue, payload.api_key, payload.api_secret, payload.passphrase, payload.environment)
    except CexPermissionDenied as exc:
        raise HTTPException(status_code=400, detail={"code": "CEX_PERMISSION_DENIED", "reason": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise _portfolio_access_http(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result = portfolio_view(db, user)
    if cex_connection_status(db, account) == "CONNECTED":
        # First-run personalization: the deterministic first portfolio brief
        # was generated during sync; route the UI to channel selection next.
        result["next_step"] = "choose_channels"
    return result


@router.post("/hyperliquid/connect")
def add_hyperliquid(payload: HyperliquidRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        account = connect_hyperliquid(db, user, payload.address)
        sync_account(db, user, account)
        return portfolio_view(db, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise _portfolio_access_http(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/plaid/transactions")
def list_plaid_transactions(
    account_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return {"transactions": plaid_investment_transactions(db, user, account_id=account_id, limit=limit)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/plaid/webhook")
async def plaid_webhook(
    request: Request,
    plaid_verification: str | None = Header(default=None, alias="Plaid-Verification"),
    db: Session = Depends(get_db),
) -> dict:
    raw_body = await request.body()
    try:
        verify_plaid_webhook(raw_body, plaid_verification)
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid payload")
        account = process_plaid_webhook(db, payload)
        if account:
            _enqueue_plaid_history_sync(account.id)
    except PlaidWebhookVerificationError as exc:
        raise HTTPException(status_code=401, detail="Invalid Plaid webhook") from exc
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Plaid webhook payload") from exc
    except Exception as exc:
        logger.exception("plaid_webhook_processing_failed")
        # A non-2xx response makes Plaid retry the webhook. We do not expose
        # Item IDs, credentials, or provider errors to the caller.
        raise HTTPException(status_code=503, detail="Plaid webhook processing unavailable") from exc
    return {"accepted": True}


@router.post("/evm/challenge")
def create_evm_challenge(payload: EVMChallengeRequest, user: User = Depends(get_current_user)) -> dict:
    try:
        message, challenge_token = _evm_challenge(user, payload.address, payload.chain_id)
        Redis.from_url(get_settings().redis_url, decode_responses=True).set(
            _evm_challenge_key(challenge_token),
            user.id,
            ex=EVM_CHALLENGE_TTL_SECONDS,
        )
        return {"message": message, "challenge_token": challenge_token, "expires_in": EVM_CHALLENGE_TTL_SECONDS}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/evm/connect")
def add_evm_wallet(payload: EVMConnectRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        _verify_evm_challenge(payload, user)
        account = connect_evm_wallet(db, user, payload.address, payload.chain_id)
        sync_account(db, user, account)
        return portfolio_view(db, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise _portfolio_access_http(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
        raise _portfolio_access_http(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/sync")
def sync_connected_account(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    account = db.query(TradingAccount).filter_by(id=account_id, user_id=user.id, account_type="READ_ONLY").one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Portfolio account not found")
    try:
        if account.venue == "PLAID":
            # Keep the interactive NAV action responsive. The task retries the
            # historical Investments pull until Plaid reports it is ready.
            sync_account(db, user, account, include_transactions=False)
            try:
                _enqueue_plaid_history_sync(account.id)
            except Exception:
                logger.exception("plaid_history_dispatch_failed account_id=%s", account.id)
                try:
                    sync_account(db, user, account, include_transactions=True)
                except PlaidDataPending:
                    pass
            result = portfolio_view(db, user)
            result["plaid_history_sync"] = "pending"
            return result
        sync_account(db, user, account)
        return portfolio_view(db, user)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/plaid-refresh")
def refresh_plaid_investments(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    account = db.query(TradingAccount).filter_by(id=account_id, user_id=user.id, account_type="READ_ONLY").one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Portfolio account not found")
    try:
        result = request_plaid_investments_refresh(db, user, account)
        _enqueue_plaid_history_sync(account.id)
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlaidRefreshRateLimited as exc:
        raise HTTPException(status_code=429, detail={"code": "PLAID_REFRESH_RATE_LIMITED", "message": str(exc)}) from exc
    except PlaidRefreshUnsupported as exc:
        raise HTTPException(status_code=409, detail={"code": "PLAID_REFRESH_UNSUPPORTED", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Plaid Investments Refresh failed") from exc


@router.delete("/accounts/{account_id}")
def disconnect_connected_account(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    account = db.query(TradingAccount).filter_by(id=account_id, user_id=user.id, account_type="READ_ONLY").one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Portfolio account not found")
    disconnect_account(db, user, account)
    return portfolio_view(db, user)
