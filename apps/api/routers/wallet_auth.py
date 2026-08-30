"""Wallet sign-in (SIWE / EIP-4361) for MetaMask, Zerion and other
injected EVM wallets.

Flow:
1. ``POST /auth/wallet/nonce`` issues a single-use EIP-4361 message bound to
   the address, the site domain and a random nonce. The FULL message is
   stored server-side (Redis, 5 min TTL) so clients cannot tamper with the
   domain/chain/statement fields.
2. ``POST /auth/wallet/verify`` consumes the stored message (single-use),
   recovers the signer with ``eth_account`` and compares it to the claimed
   address. A match signs the user in — creating the account on first use
   (wallet sign-in IS wallet sign-up).

No blockchain transaction or contract call is involved: ``personal_sign`` is
gas-free and cannot move funds. Contract-wallet (EIP-1271) signatures are NOT
accepted in this release — only EOA signatures.

Fail-closed: when Redis is unavailable in production, wallet auth returns 503
rather than accepting unverifiable nonces.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_db, set_session_cookie
from apps.api.routers.auth import serialize_user
from packages.database.models import User, UserIdentity, UserPreference

router = APIRouter(tags=["wallet-auth"])
logger = logging.getLogger("puregamma.wallet_auth")

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_NONCE_TTL_SECONDS = 300
_WALLET_PROVIDERS = {"metamask", "zerion", "injected"}
_PLACEHOLDER_EMAIL_DOMAIN = "wallet.puregamma.local"


class WalletNonceRequest(BaseModel):
    address: str = Field(min_length=42, max_length=42)
    chain_id: int = Field(default=1, ge=1)


class WalletVerifyRequest(BaseModel):
    address: str = Field(min_length=42, max_length=42)
    signature: str = Field(min_length=10, max_length=256)
    wallet: str = Field(default="injected", max_length=32)


def _normalize_address(value: str) -> str:
    address = (value or "").strip().lower()
    if not _ADDRESS_RE.match(address):
        raise HTTPException(status_code=400, detail={"code": "INVALID_WALLET_ADDRESS"})
    return address


def _redis():
    from apps.api.redis_client import get_redis

    return get_redis()


def _nonce_key(address: str) -> str:
    return f"pg:auth:wallet:{address}"


def _rate_limit(request: Request, address: str, action: str, limit: int = 10, window: int = 600) -> None:
    settings = get_settings()
    if settings.app_environment.lower() != "production":
        return
    forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
    client = forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    fingerprint = hashlib.sha256(f"{client}:{address}:{action}".encode()).hexdigest()
    key = f"pg:auth:wallet:rl:{fingerprint}"
    try:
        count = int(_redis().incr(key))
        if count == 1:
            _redis().expire(key, window)
        if count > limit:
            raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED"}, headers={"Retry-After": str(window)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("wallet_rate_limit_unavailable", extra={"error": type(exc).__name__})
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc


def _site_origin() -> tuple[str, str]:
    settings = get_settings()
    parsed = urlparse(settings.site_url if "://" in settings.site_url else f"https://{settings.site_url}")
    host = parsed.netloc or parsed.path
    origin = f"{parsed.scheme or 'https'}://{host}"
    return host, origin


def _build_message(address: str, chain_id: int, nonce: str) -> str:
    host, origin = _site_origin()
    issued_at = datetime.now(timezone.utc).isoformat()
    try:
        from eth_utils import to_checksum_address

        checksum_address = to_checksum_address(address)
    except Exception:
        checksum_address = address
    return (
        f"{host} wants you to sign in with your Ethereum account:\n"
        f"{checksum_address}\n\n"
        "Sign in to PureGamma AI with your wallet. This request will not "
        "trigger a blockchain transaction or cost any gas fees.\n\n"
        f"URI: {origin}\n"
        "Version: 1\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at}"
    )


@router.post("/auth/wallet/nonce")
def wallet_nonce(payload: WalletNonceRequest, request: Request) -> dict:
    address = _normalize_address(payload.address)
    _rate_limit(request, address, "nonce", limit=10, window=600)
    nonce = secrets.token_hex(8)
    message = _build_message(address, payload.chain_id, nonce)
    try:
        _redis().setex(_nonce_key(address), _NONCE_TTL_SECONDS, message)
    except Exception as exc:
        logger.error("wallet_nonce_store_failed", extra={"error": type(exc).__name__})
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    return {"message": message, "nonce": nonce, "expires_in": _NONCE_TTL_SECONDS}


@router.post("/auth/wallet/verify")
def wallet_verify(
    payload: WalletVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    address = _normalize_address(payload.address)
    _rate_limit(request, address, "verify", limit=10, window=600)
    wallet = (payload.wallet or "injected").strip().lower()
    if wallet not in _WALLET_PROVIDERS:
        raise HTTPException(status_code=400, detail={"code": "UNSUPPORTED_WALLET"})

    # Single-use: the message leaves the store exactly once (GETDEL, with a
    # GET+DELETE fallback for Redis servers older than 6.2).
    try:
        client = _redis()
        try:
            stored = client.getdel(_nonce_key(address))
        except AttributeError:
            stored = client.get(_nonce_key(address))
            client.delete(_nonce_key(address))
    except Exception as exc:
        logger.error("wallet_nonce_read_failed", extra={"error": type(exc).__name__})
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    if not stored:
        raise HTTPException(status_code=401, detail={"code": "WALLET_NONCE_EXPIRED"})
    message = stored.decode() if isinstance(stored, bytes) else str(stored)

    try:
        recovered = Account.recover_message(
            encode_defunct(text=message), signature=payload.signature
        ).lower()
    except Exception:
        raise HTTPException(status_code=401, detail={"code": "WALLET_SIGNATURE_INVALID"})
    if recovered != address:
        raise HTTPException(status_code=401, detail={"code": "WALLET_SIGNATURE_MISMATCH"})

    identity = (
        db.query(UserIdentity)
        .filter_by(provider="evm_wallet", provider_subject=address)
        .one_or_none()
    )
    if identity:
        user = db.get(User, identity.user_id)
        if not user:
            raise HTTPException(status_code=401, detail={"code": "WALLET_ACCOUNT_MISSING"})
    else:
        short = f"{address[:6]}...{address[-4:]}"
        user = User(
            # Wallet accounts have no inbox; the placeholder keeps the
            # NOT NULL + unique constraint honest and is clearly synthetic.
            email=f"{address}@{_PLACEHOLDER_EMAIL_DOMAIN}",
            name=short,
            role="user",
            plan="Free",
            credit_balance=150,
            auth_provider="wallet",
            # A verified wallet signature is the credential; there is no
            # email to verify for this auth path.
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
        db.add(
            UserIdentity(
                user_id=user.id,
                provider="evm_wallet",
                provider_subject=address,
                provider_email=None,
                provider_email_verified=False,
            )
        )
        db.add(UserPreference(user_id=user.id, locale="en"))
        logger.info("wallet_user_created", extra={"user_id": user.id, "wallet": wallet})

    user.last_login_at = datetime.now(timezone.utc)
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)
    set_session_cookie(response, user)
    logger.info("wallet_login_succeeded", extra={"user_id": user.id, "wallet": wallet})
    return {"user": serialize_user(user)}
