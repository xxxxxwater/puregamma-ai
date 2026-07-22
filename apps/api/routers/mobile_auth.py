from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta, timezone
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import create_access_token, get_current_user, get_db, set_session_cookie
from apps.api.i18n import normalize_locale
from apps.api.routers.auth import serialize_user
from apps.api.routers.google_auth import GOOGLE_AUTHORIZE_URL, _challenge, _exchange_code_for_token, _verify_google_id_token, upsert_google_user
from packages.database.models import MobileOAuthSession, MobileWebSession, User, UserPreference, utcnow
from packages.security.passwords import hash_password, verify_password


router = APIRouter(prefix="/auth/mobile", tags=["auth"])
SESSION_TTL_SECONDS = 600
TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
WEB_SESSION_TTL_SECONDS = 60


class MobileOAuthStart(BaseModel):
    redirect_uri: str = Field(min_length=8, max_length=512)
    code_challenge: str = Field(min_length=43, max_length=128)
    client_state: str = Field(min_length=32, max_length=256)
    nonce: str = Field(min_length=32, max_length=256)


class MobileOAuthExchange(BaseModel):
    code: str = Field(min_length=32, max_length=512)
    code_verifier: str = Field(min_length=43, max_length=128)
    nonce: str = Field(min_length=32, max_length=256)


class MobileWebSessionRequest(BaseModel):
    locale: str = Field(default="en", pattern="^(en|zh)$")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _expired(value) -> bool:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware < utcnow()


def _allowed_redirect(uri: str) -> bool:
    return uri in set(get_settings().mobile_oauth_redirect_uris)


def _redirect_with_query(uri: str, **values: str) -> str:
    parts = urlsplit(uri)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(values)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@router.post("/google/start")
def mobile_google_start(payload: MobileOAuthStart, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail={"code": "GOOGLE_OAUTH_NOT_CONFIGURED"})
    if not _allowed_redirect(payload.redirect_uri):
        raise HTTPException(status_code=400, detail={"code": "MOBILE_REDIRECT_URI_INVALID"})
    if not payload.code_challenge.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail={"code": "PKCE_CHALLENGE_INVALID"})
    state = secrets.token_urlsafe(48)
    provider_nonce = secrets.token_urlsafe(48)
    provider_verifier = secrets.token_urlsafe(64)
    row = MobileOAuthSession(provider="google", state=state, client_state=payload.client_state, client_nonce=payload.nonce, provider_nonce=provider_nonce, provider_code_verifier=provider_verifier, code_challenge=payload.code_challenge, redirect_uri=payload.redirect_uri, expires_at=utcnow() + timedelta(seconds=SESSION_TTL_SECONDS))
    db.add(row)
    db.commit()
    query = urlencode({"client_id": settings.google_client_id, "redirect_uri": settings.mobile_google_oauth_redirect_uri, "response_type": "code", "scope": "openid email profile", "state": state, "prompt": "select_account", "nonce": provider_nonce, "code_challenge": _challenge(provider_verifier), "code_challenge_method": "S256"})
    return {"auth_url": f"{GOOGLE_AUTHORIZE_URL}?{query}", "expires_at": row.expires_at.isoformat()}


@router.get("/google/callback")
def mobile_google_callback(state: str, code: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    settings = get_settings()
    row = db.query(MobileOAuthSession).filter_by(state=state, provider="google").one_or_none()
    if not row or row.consumed_at or _expired(row.expires_at):
        raise HTTPException(status_code=400, detail={"code": "MOBILE_OAUTH_SESSION_INVALID"})
    if error or not code:
        row.provider_code_verifier = "consumed"
        row.consumed_at = utcnow()
        db.commit()
        return RedirectResponse(_redirect_with_query(row.redirect_uri, error="oauth_canceled", state=row.client_state), status_code=302)
    try:
        token_response = _exchange_code_for_token(code, settings.mobile_google_oauth_redirect_uri, settings.google_client_id, settings.google_client_secret, row.provider_code_verifier)
        id_token_value = token_response.get("id_token")
        if not id_token_value:
            raise ValueError("Google token response did not include id_token")
        identity = _verify_google_id_token(id_token_value, settings.google_client_id)
        if not identity.get("nonce") or not secrets.compare_digest(str(identity["nonce"]), row.provider_nonce):
            raise ValueError("Invalid Google token nonce")
        user = upsert_google_user(db, identity)
    except Exception as exc:
        db.rollback()
        return RedirectResponse(_redirect_with_query(row.redirect_uri, error="google_verification_failed", state=row.client_state), status_code=302)
    exchange_code = secrets.token_urlsafe(48)
    row.exchange_code_hash = _hash(exchange_code)
    row.user_id = user.id
    row.provider_code_verifier = "consumed"
    db.commit()
    return RedirectResponse(_redirect_with_query(row.redirect_uri, code=exchange_code, state=row.client_state), status_code=302)


@router.post("/google/exchange")
def mobile_google_exchange(payload: MobileOAuthExchange, db: Session = Depends(get_db)) -> dict:
    row = db.query(MobileOAuthSession).filter_by(exchange_code_hash=_hash(payload.code), provider="google").one_or_none()
    if not row or row.consumed_at or _expired(row.expires_at) or not row.user_id:
        raise HTTPException(status_code=400, detail={"code": "MOBILE_EXCHANGE_CODE_INVALID"})
    if not secrets.compare_digest(_challenge(payload.code_verifier), row.code_challenge) or not secrets.compare_digest(payload.nonce, row.client_nonce):
        raise HTTPException(status_code=400, detail={"code": "MOBILE_PKCE_VERIFICATION_FAILED"})
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(status_code=400, detail={"code": "MOBILE_OAUTH_USER_MISSING"})
    row.consumed_at = utcnow()
    row.exchange_code_hash = None
    db.commit()
    return {"access_token": create_access_token(user, TOKEN_TTL_SECONDS), "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS, "user": serialize_user(user)}


@router.post("/web-session")
def create_mobile_web_session(
    payload: MobileWebSessionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Exchange an Android Bearer token for a short-lived, one-time web cookie handoff."""
    code = secrets.token_urlsafe(48)
    db.query(MobileWebSession).filter(MobileWebSession.expires_at < utcnow()).delete(synchronize_session=False)
    row = MobileWebSession(
        code_hash=_hash(code),
        user_id=user.id,
        locale=payload.locale,
        expires_at=utcnow() + timedelta(seconds=WEB_SESSION_TTL_SECONDS),
    )
    db.add(row)
    db.commit()
    return {"handoff_path": f"/auth/mobile/web-session/consume?code={code}", "expires_in": WEB_SESSION_TTL_SECONDS}


@router.get("/web-session/consume")
def consume_mobile_web_session(code: str, db: Session = Depends(get_db)):
    row = (
        db.query(MobileWebSession)
        .filter(MobileWebSession.code_hash == _hash(code))
        .with_for_update()
        .one_or_none()
    )
    if not row or row.consumed_at or _expired(row.expires_at):
        raise HTTPException(status_code=400, detail={"code": "MOBILE_WEB_SESSION_INVALID"})
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(status_code=400, detail={"code": "MOBILE_WEB_SESSION_USER_MISSING"})
    row.consumed_at = utcnow()
    response = RedirectResponse(f"{get_settings().site_url}/{row.locale}/dashboard", status_code=302)
    set_session_cookie(response, user)
    db.commit()
    return response


# ── Mobile Email Auth ──────────────────────────────

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$")
_MIN_PASSWORD_LENGTH = 8

_COMMON_PASSWORDS = frozenset({
    "password", "password1", "password12", "password123",
    "12345678", "123456789", "1234567890",
    "qwertyuiop", "asdfghjkl", "zxcvbnm",
    "iloveyou", "sunshine", "trustno1",
    "puregamma", "puregamma1", "puregammaai",
})


class MobileEmailLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class MobileEmailRegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128)
    name: str = Field(min_length=1, max_length=120, default="")
    locale: str = Field(default="en", max_length=5)


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _validate_email_format(email: str) -> None:
    if not _EMAIL_RE.match(email) or ".." in email:
        raise HTTPException(status_code=400, detail={"code": "INVALID_EMAIL"})


def _check_password_strength(password: str) -> str | None:
    if len(password) < _MIN_PASSWORD_LENGTH:
        return "length"
    if password.lower() in _COMMON_PASSWORDS:
        return "common"
    if not re.search(r"[A-Za-z]", password):
        return "letter"
    if not re.search(r"[0-9]", password):
        return "digit"
    if password.lower() == password:
        return "uppercase"
    return None


@router.post("/email/login")
def mobile_email_login(
    payload: MobileEmailLoginRequest,
    db: Session = Depends(get_db),
) -> dict:
    email = _normalize_email(payload.email)
    _validate_email_format(email)

    user = db.query(User).filter(
        User.email == email,
        User.password_hash.isnot(None),
    ).one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS"})

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS"})

    if not user.email_verified_at:
        raise HTTPException(status_code=403, detail={"code": "EMAIL_NOT_VERIFIED", "email": email})

    user.last_login_at = utcnow()
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)

    return {
        "access_token": create_access_token(user, TOKEN_TTL_SECONDS),
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "user": serialize_user(user),
    }


@router.post("/email/register")
def mobile_email_register(
    payload: MobileEmailRegisterRequest,
    db: Session = Depends(get_db),
) -> dict:
    email = _normalize_email(payload.email)
    _validate_email_format(email)

    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail={"code": "EMAIL_ALREADY_REGISTERED"})

    weakness = _check_password_strength(payload.password)
    if weakness:
        raise HTTPException(
            status_code=400,
            detail={"code": "PASSWORD_TOO_WEAK", "rule": weakness},
        )

    pw_hash = hash_password(payload.password)
    locale = normalize_locale(payload.locale)

    user = User(
        email=email,
        name=payload.name.strip() or "PureGamma User",
        role="user",
        plan="Free",
        credit_balance=150,
        auth_provider="email",
        password_hash=pw_hash,
        email_verified_at=utcnow(),
    )
    db.add(user)
    db.flush()

    if not user.preference:
        db.add(UserPreference(user_id=user.id, email_recipient=email, locale=locale))

    user.last_login_at = utcnow()
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)

    return {
        "access_token": create_access_token(user, TOKEN_TTL_SECONDS),
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "user": serialize_user(user),
    }
