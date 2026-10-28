from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Generator

from fastapi import Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import User
from packages.database.seed import seed_all, seed_reference_data
from packages.database.session import SessionLocal, init_db


logger = logging.getLogger(__name__)

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_access_token(user: User, expires_in_seconds: int = 86400) -> str:
    settings = get_settings()
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "sv": user.session_version,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_seconds,
    }
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


# ---------------------------------------------------------------------------
# Per-user DSH Host tokens (multi-tenant DSH Web behind the session broker).
#
# A Host token is a normal HS256 session JWT for exactly one user plus an
# audience/scope pair. It is short-lived, only accepted as a Bearer header
# (never as the session cookie), carries the user's session_version so logout
# revokes it, and only reaches the read/act routes the legacy-api providers
# need. It cannot mint credentials (internal routes, gateway key writes),
# reach admin, account or session routes, or export the account.
DSH_HOST_TOKEN_AUDIENCE = "puregamma-dsh-host"
DSH_HOST_TOKEN_SCOPE = "dsh-host"
DSH_HOST_TOKEN_MAX_TTL_SECONDS = 900

# (path prefix, allowed methods or None for any). Matched on whole segments;
# a leading "/api" is ignored so both mount styles of a router match.
_DSH_HOST_ROUTES: tuple[tuple[str, frozenset[str] | None], ...] = (
    ("/me", frozenset({"GET"})),
    ("/market", None),
    ("/news", frozenset({"GET"})),
    ("/options", None),
    ("/research", None),
    ("/backtest", None),
    ("/backtest-lab", None),
    ("/portfolio", None),
    ("/billing", None),
    ("/notifications", None),
    ("/memory", None),
    ("/secretary", None),
    ("/gateway", frozenset({"GET"})),
)


def create_dsh_host_token(user: User, *, ttl_seconds: int, auth_time: int) -> tuple[str, int]:
    settings = get_settings()
    now = int(time.time())
    ttl = max(60, min(int(ttl_seconds), DSH_HOST_TOKEN_MAX_TTL_SECONDS))
    payload = {
        "sub": user.id,
        "sv": user.session_version,
        "aud": DSH_HOST_TOKEN_AUDIENCE,
        "scope": DSH_HOST_TOKEN_SCOPE,
        "auth_time": int(auth_time),
        "jti": secrets.token_urlsafe(12),
        "iat": now,
        "exp": now + ttl,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}", payload["exp"]


def is_scoped_token(claims: dict) -> bool:
    return "aud" in claims or "scope" in claims


def dsh_host_route_allowed(method: str, path: str) -> bool:
    candidates = [path]
    if path == "/api" or path.startswith("/api/"):
        candidates.append(path[4:] or "/")
    for candidate in candidates:
        for prefix, methods in _DSH_HOST_ROUTES:
            if candidate == prefix or candidate.startswith(prefix + "/"):
                if prefix == "/me" and candidate != "/me":
                    continue
                if methods is None or method.upper() in methods:
                    return True
    return False


def check_dsh_host_claims(claims: dict) -> None:
    """Reject anything that is not a well-formed, short-lived Host token."""
    if claims.get("aud") != DSH_HOST_TOKEN_AUDIENCE or claims.get("scope") != DSH_HOST_TOKEN_SCOPE:
        raise HTTPException(status_code=401, detail="Unsupported token audience")
    try:
        lifetime = int(claims["exp"]) - int(claims["iat"])
        int(claims["auth_time"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Malformed host token") from exc
    if lifetime > DSH_HOST_TOKEN_MAX_TTL_SECONDS:
        raise HTTPException(status_code=401, detail="Host token lifetime exceeds policy")


def verify_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(settings.jwt_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected), signature_b64):
            raise ValueError("Invalid token signature")
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Token expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc


def ensure_bootstrap() -> None:
    init_db()
    db = SessionLocal()
    try:
        if get_settings().app_environment.lower() in {"production", "staging"}:
            seed_reference_data(db)
        else:
            seed_all(db)
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db), authorization: str | None = Header(default=None)) -> User:
    token = None
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Authorization must be a Bearer token")
    else:
        token = request.cookies.get(get_settings().session_cookie_name)
    if token:
        claims = verify_access_token(token)
        if is_scoped_token(claims):
            # Host tokens are only ever Bearer headers from a broker-managed Host.
            if not authorization:
                raise HTTPException(status_code=401, detail="Scoped tokens are not session cookies")
            check_dsh_host_claims(claims)
            if not dsh_host_route_allowed(request.method, request.url.path):
                raise HTTPException(status_code=403, detail={"code": "DSH_HOST_TOKEN_SCOPE", "message": "This route needs a full PureGamma session."})
        user = db.get(User, claims.get("sub"))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if int(claims.get("sv", -1)) != int(user.session_version or 0):
            raise HTTPException(status_code=401, detail="Session has been revoked")
        return user
    if get_settings().auth_allow_demo_fallback:
        user = db.query(User).filter(User.email == "demo@puregamma.ai").one_or_none()
        if user:
            return user
        seed_all(db)
        return db.query(User).filter(User.email == "demo@puregamma.ai").one()
    raise HTTPException(status_code=401, detail="Authentication required")


def set_session_cookie(response: Response, user: User) -> str:
    settings = get_settings()
    token = create_access_token(user, settings.session_max_age_seconds)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.app_environment == "production" or settings.site_url.lower().startswith("https://"),
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
    )
    return token


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name, path="/", domain=settings.session_cookie_domain
    )


def require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

def require_pm_account_viewer(user: User = Depends(get_current_user)) -> User:
    """Authorize access to the separately published private PM account.

    Visibility in the web client is deliberately not an authorization control.
    The allowlist is evaluated on every request and a missing configuration
    fails closed.
    """
    from apps.api.services.pm_riskbot_service import allowed_emails, is_allowed_email

    if not is_allowed_email(user.email):
        logger.warning(
            "pm_account_access_denied user=%s allowlist_size=%d",
            user.id,
            len(allowed_emails()),
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PM_ACCOUNT_NOT_AUTHORIZED",
                "message": "This account is not authorized to view the private portfolio.",
            },
        )
    return user
