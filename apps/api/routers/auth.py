from __future__ import annotations

import logging
import secrets
import hashlib
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from apps.api.dependencies import (
    clear_session_cookie,
    get_current_user,
    get_db,
    set_session_cookie,
)
from apps.api.i18n import normalize_locale
from apps.api.config import get_settings
from packages.database.models import Base, User, UserIdentity, UserPreference, utcnow


router = APIRouter(tags=["auth"])
logger = logging.getLogger("puregamma.auth")


class MockLoginRequest(BaseModel):
    email: str = "demo@puregamma.ai"
    name: str = "Demo User"
    locale: str = "en"


class InternalAdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


class LocalePreferenceRequest(BaseModel):
    locale: str


class DeleteAccountRequest(BaseModel):
    confirmation: str = Field(min_length=3, max_length=320)


class OnboardingRequest(BaseModel):
    preferred_assets: list[str] = Field(default_factory=list)
    preferred_style: str = "risk-controlled"
    notification_channels: list[str] = Field(default_factory=lambda: ["email"])
    email_recipient: str = ""
    telegram_chat_id: str = ""
    imessage_recipient: str = ""


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "plan": user.plan,
        "credit_balance": user.credit_balance,
        "stripe_customer_id": user.stripe_customer_id,
        "google_user_id": user.google_user_id,
        "avatar_url": user.avatar_url,
        "auth_provider": user.auth_provider,
        "has_password": bool(user.password_hash),
        "email_verified": bool(user.email_verified_at),
        "email_verified_at": user.email_verified_at.isoformat()
        if user.email_verified_at
        else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "login_methods": sorted(
            {identity.provider for identity in user.identities} | {user.auth_provider}
        ),
        "locale": user.preference.locale if user.preference else "en",
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }


def _internal_admin_rate_limit(request: Request, username: str, *, success: bool = False) -> None:
    """Five failed attempts per IP/account in 15 minutes; production fails closed."""
    settings = get_settings()
    if settings.app_environment.lower() != "production":
        return
    forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
    client = forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    fingerprint = hashlib.sha256(f"{client}:{username.lower()}".encode()).hexdigest()
    key = f"pg:auth:internal-admin:{fingerprint}"
    try:
        from apps.api.redis_client import get_redis

        redis = get_redis()
        if success:
            redis.delete(key)
            return
        count = int(redis.incr(key))
        if count == 1:
            redis.expire(key, 900)
        if count > 5:
            raise HTTPException(status_code=429, detail="Too many login attempts", headers={"Retry-After": "900"})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("internal_admin_rate_limit_unavailable", extra={"error": type(exc).__name__})
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc


@router.post("/auth/internal-admin-login")
def internal_admin_login(
    payload: InternalAdminLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.internal_admin_login_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    from packages.security.passwords import verify_password

    username_matches = secrets.compare_digest(payload.username, settings.internal_admin_username)
    password_matches = verify_password(payload.password, settings.internal_admin_password_hash)
    if not (username_matches and password_matches):
        _internal_admin_rate_limit(request, payload.username)
        logger.warning("internal_admin_login_failed")
        raise HTTPException(status_code=401, detail="Invalid administrator credentials")

    user = db.query(User).filter(User.email == settings.internal_admin_user_email).one_or_none()
    if not user or user.role != "admin":
        logger.error("internal_admin_account_not_authorized")
        raise HTTPException(status_code=403, detail="Administrator account is not authorized")

    _internal_admin_rate_limit(request, payload.username, success=True)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    set_session_cookie(response, user)
    logger.info("internal_admin_login_succeeded", extra={"user_id": user.id})
    return {"user": serialize_user(user), "redirect_to": "/admin"}


@router.post("/auth/mock-login")
def mock_login(
    payload: MockLoginRequest, response: Response, db: Session = Depends(get_db)
) -> dict:
    settings = get_settings()
    if settings.app_environment.lower() == "production":
        raise HTTPException(status_code=404, detail="Not found")
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if not user:
        user = User(
            email=payload.email,
            name=payload.name,
            role="user",
            plan="Free",
            credit_balance=150,
            auth_provider="mock",
        )
        db.add(user)
        db.flush()
    user.auth_provider = user.auth_provider or "mock"
    user.name = payload.name
    if user.email != "demo@puregamma.ai":
        user.role = "user"
    locale = normalize_locale(payload.locale)
    if not user.preference:
        db.add(
            UserPreference(
                user_id=user.id,
                email_recipient=user.email,
                locale=locale,
            )
        )
    else:
        user.preference.locale = locale
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)
    set_session_cookie(response, user)
    return {"user": serialize_user(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"user": serialize_user(user)}


@router.post("/auth/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    clear_session_cookie(response)
    return {"ok": True}


def _user_scope(table, user_id: str, seen: frozenset[str] = frozenset()):
    """Build a deletion predicate for rows owned directly or transitively by a user."""
    if table.name in seen:
        return None
    if "user_id" in table.c:
        return table.c.user_id == user_id
    predicates = []
    next_seen = seen | {table.name}
    for foreign_key in table.foreign_keys:
        parent = foreign_key.column.table
        parent_scope = _user_scope(parent, user_id, next_seen)
        if parent_scope is not None:
            predicates.append(foreign_key.parent.in_(select(foreign_key.column).where(parent_scope)))
    return or_(*predicates) if predicates else None


def _delete_external_account(user: User, db: Session) -> None:
    settings = get_settings()
    for identity in db.query(UserIdentity).filter_by(user_id=user.id, provider="apple").all():
        try:
            from apps.api.routers.apple_auth import revoke_apple_identity

            revoke_apple_identity(identity, settings)
        except (ValueError, RuntimeError, httpx.HTTPError) as exc:
            logger.warning("apple_identity_revoke_failed", extra={"user_id": user.id, "error": type(exc).__name__})
            raise HTTPException(status_code=503, detail={"code": "ACCOUNT_PROVIDER_REVOCATION_FAILED"}) from exc
    if user.stripe_customer_id and settings.billing_mode == "stripe":
        try:
            import stripe

            stripe.api_key = settings.stripe_secret_key
            stripe.api_version = settings.stripe_api_version
            stripe.Customer.delete(user.stripe_customer_id)
        except Exception as exc:
            logger.warning("stripe_customer_delete_failed", extra={"user_id": user.id, "error": type(exc).__name__})
            raise HTTPException(status_code=503, detail={"code": "ACCOUNT_BILLING_CLEANUP_FAILED"}) from exc


def _purge_user(db: Session, user_id: str) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        if table.name == User.__tablename__:
            continue
        predicate = _user_scope(table, user_id)
        if predicate is not None:
            db.execute(table.delete().where(predicate))
    db.execute(User.__table__.delete().where(User.id == user_id))


@router.delete("/me")
def delete_account(
    payload: DeleteAccountRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not secrets.compare_digest(payload.confirmation.strip().lower(), user.email.lower()):
        raise HTTPException(status_code=400, detail={"code": "ACCOUNT_DELETE_CONFIRMATION_MISMATCH"})
    _delete_external_account(user, db)
    user_id = user.id
    _purge_user(db, user_id)
    db.commit()
    clear_session_cookie(response)
    logger.info("account_deleted", extra={"user_id": user_id})
    return {"ok": True}


# Fields that must never leave the server, even in a user's own export.
_EXPORT_SENSITIVE_COLUMNS = {
    "password_hash",
    "email_verification_token",
    "email_verification_token_expires_at",
    "key_hash",
    "api_key",  # gateway api keys are masked below regardless
}


@router.get("/me/export")
def export_account(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """GDPR/PIPL data-export: every row owned by the user, as JSON.

    Sensitive credential columns are omitted; the export is returned directly
    so the requester can download it once. A later batch job can email an
    archive for very large accounts if needed.
    """
    from packages.database.models import Base

    user_id = user.id
    tables: dict[str, list[dict]] = {}
    for table in Base.metadata.sorted_tables:
        if table.name == User.__tablename__:
            continue
        scope = _user_scope(table, user_id)
        if scope is None:
            continue
        columns = [col.name for col in table.columns if col.name not in _EXPORT_SENSITIVE_COLUMNS]
        rows = db.execute(table.select().where(scope).limit(1000)).mappings().all()
        records = []
        for row in rows:
            record = {col: _export_value(row[col]) for col in columns}
            if table.name == "gateway_api_keys" and "key_prefix" in record:
                record.pop("key_prefix", None)
            records.append(record)
        if records:
            tables[table.name] = records

    user_data = {
        "email": user.email,
        "name": user.name,
        "plan": user.plan,
        "role": user.role,
        "locale": getattr(user, "locale", None),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }
    return {"user": user_data, "tables": tables, "exported_at": utcnow().isoformat()}


def _export_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@router.post("/auth/preferences/locale")
def save_locale(
    payload: LocalePreferenceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    locale = normalize_locale(payload.locale)
    if not user.preference:
        db.add(
            UserPreference(
                user_id=user.id,
                email_recipient=user.email,
                locale=locale,
            )
        )
    else:
        user.preference.locale = locale
    db.commit()
    db.refresh(user)
    return {"locale": locale, "user": serialize_user(user)}


@router.post("/auth/onboarding")
def save_onboarding(
    payload: OnboardingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    allowed_assets = {"BTC", "ETH", "SOL", "HYPE", "MSTR", "STRC"}
    assets = [item.upper() for item in payload.preferred_assets if item.upper() in allowed_assets]
    allowed_channels = set(get_user_channels(user.plan))
    channels = [item for item in payload.notification_channels if item in allowed_channels]
    preference = user.preference
    if not preference:
        preference = UserPreference(user_id=user.id)
        db.add(preference)
    preference.preferred_assets = assets or ["BTC", "ETH", "SOL"]
    preference.preferred_style = payload.preferred_style[:80]
    preference.notification_channels = channels or ["email"]
    # Anti-abuse: notification email may only go to the verified account email
    # until a recipient-verification flow exists; arbitrary addresses would let
    # anyone weaponize the platform SMTP for phishing.
    preference.email_recipient = user.email
    preference.telegram_chat_id = payload.telegram_chat_id[:160] or None
    preference.imessage_recipient = payload.imessage_recipient[:40] or None
    db.commit()
    return {"ok": True, "user": serialize_user(user)}


def get_user_channels(plan_name: str) -> list[str]:
    from packages.billing.entitlements import entitlement_for_plan

    return entitlement_for_plan(plan_name)["notification_channels"]
