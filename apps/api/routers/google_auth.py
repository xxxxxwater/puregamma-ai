from __future__ import annotations

import secrets
import hashlib
import base64
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_db, set_session_cookie
from packages.database.models import UsageEvent, User, UserIdentity, UserPreference


router = APIRouter(tags=["auth"])

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
STATE_COOKIE = "pg_google_oauth_state"
NONCE_COOKIE = "pg_google_oauth_nonce"
PKCE_COOKIE = "pg_google_oauth_pkce"
RETURN_COOKIE = "pg_google_oauth_return"
STATE_MAX_AGE_SECONDS = 600


def _configured_google_settings() -> tuple[str, str, str]:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    return settings.google_client_id, settings.google_client_secret, settings.google_oauth_redirect_uri


def _exchange_code_for_token(code: str, redirect_uri: str, client_id: str, client_secret: str, code_verifier: str) -> dict:
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        response.raise_for_status()
        return response.json()


def _verify_google_id_token(id_token_value: str, client_id: str) -> dict:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    payload = id_token.verify_oauth2_token(id_token_value, google_requests.Request(), client_id)
    issuer = payload.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise ValueError("Invalid Google token issuer")
    if payload.get("aud") != client_id:
        raise ValueError("Invalid Google token audience")
    return payload


def _email_verified(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


def _should_update_name(user: User, incoming_name: str | None) -> bool:
    if not incoming_name:
        return False
    local_part = user.email.split("@")[0]
    return user.name in {"", "PureGamma User", local_part, user.email}


def _safe_return_to(value: str | None) -> str:
    return value if value and value.startswith("/") and not value.startswith("//") else "/chat"


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def upsert_google_user(db: Session, payload: dict) -> User:
    """Create/link a verified Google identity for both web and native flows."""
    if not _email_verified(payload.get("email_verified")):
        raise ValueError("Google email is not verified")
    email = payload.get("email")
    google_user_id = payload.get("sub")
    if not email or not google_user_id:
        raise ValueError("Google token missing email or subject")
    identity = db.query(UserIdentity).filter_by(provider="google", provider_subject=google_user_id).one_or_none()
    user = db.get(User, identity.user_id) if identity else None
    linked_existing_email = False
    if not user:
        user = db.query(User).filter(User.email == email).one_or_none()
        linked_existing_email = user is not None
    if not user:
        user = User(email=email, name=payload.get("name") or email.split("@")[0], role="user", plan="Free", credit_balance=150, google_user_id=google_user_id, avatar_url=payload.get("picture"), auth_provider="google", email_verified_at=datetime.now(timezone.utc), last_login_at=datetime.now(timezone.utc))
        db.add(user)
        db.flush()
        db.add(UserPreference(user_id=user.id, email_recipient=email, notification_channels=["email"]))
    else:
        was_unverified = not user.email_verified_at
        if _should_update_name(user, payload.get("name")):
            user.name = payload.get("name")
        user.google_user_id = google_user_id
        user.avatar_url = payload.get("picture") or user.avatar_url
        user.auth_provider = "google"
        user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
        user.last_login_at = datetime.now(timezone.utc)
        if linked_existing_email and was_unverified:
            user.password_hash = None
        if not user.preference:
            db.add(UserPreference(user_id=user.id, email_recipient=email, notification_channels=["email"]))
    if not identity:
        db.add(UserIdentity(user_id=user.id, provider="google", provider_subject=google_user_id, provider_email=email, provider_email_verified=True))
        db.flush()
        db.add(UsageEvent(user_id=user.id, event_type="auth.google.link", quantity=1, idempotency_key=f"google-link:{google_user_id}", metadata_json={"linked_existing_email": linked_existing_email}))
    else:
        identity.provider_email = email
        identity.provider_email_verified = True
    return user


@router.get("/auth/google/authorize")
def google_authorize(response: Response, return_to: str | None = None) -> dict:
    client_id, _, redirect_uri = _configured_google_settings()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    cookie_options = {"max_age": STATE_MAX_AGE_SECONDS, "httponly": True, "secure": redirect_uri.startswith("https://"), "samesite": "lax", "path": "/"}
    response.set_cookie(STATE_COOKIE, state, **cookie_options)
    response.set_cookie(NONCE_COOKIE, nonce, **cookie_options)
    response.set_cookie(PKCE_COOKIE, verifier, **cookie_options)
    response.set_cookie(RETURN_COOKIE, _safe_return_to(return_to), **cookie_options)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
            "nonce": nonce,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return {"auth_url": f"{GOOGLE_AUTHORIZE_URL}?{query}", "state": state}


@router.get("/auth/google/callback")
def google_callback(code: str, state: str, request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    client_id, client_secret, redirect_uri = _configured_google_settings()
    cookie_state = request.cookies.get(STATE_COOKIE)
    nonce = request.cookies.get(NONCE_COOKIE)
    verifier = request.cookies.get(PKCE_COOKIE)
    return_to = _safe_return_to(request.cookies.get(RETURN_COOKIE))
    for cookie in (STATE_COOKIE, NONCE_COOKIE, PKCE_COOKIE, RETURN_COOKIE):
        response.delete_cookie(cookie, path="/")
    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    if not nonce or not verifier:
        raise HTTPException(status_code=400, detail="OAuth session expired")
    try:
        token_response = _exchange_code_for_token(code, redirect_uri, client_id, client_secret, verifier)
        id_token_value = token_response.get("id_token")
        if not id_token_value:
            raise ValueError("Google token response did not include id_token")
        payload = _verify_google_id_token(id_token_value, client_id)
        if not payload.get("nonce") or not secrets.compare_digest(str(payload["nonce"]), nonce):
            raise ValueError("Invalid Google token nonce")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Google OAuth verification failed: {exc}") from exc

    try:
        user = upsert_google_user(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)
    redirect_response = RedirectResponse(
        url=f"{get_settings().site_url.rstrip('/')}{return_to}",
        status_code=303,
    )
    for cookie in (STATE_COOKIE, NONCE_COOKIE, PKCE_COOKIE, RETURN_COOKIE):
        redirect_response.delete_cookie(cookie, path="/")
    set_session_cookie(redirect_response, user)
    return redirect_response
