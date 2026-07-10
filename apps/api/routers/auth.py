from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.dependencies import clear_session_cookie, create_access_token, get_current_user, get_db, set_session_cookie
from apps.api.i18n import normalize_locale
from packages.database.models import User, UserPreference


router = APIRouter(tags=["auth"])


class MockLoginRequest(BaseModel):
    email: str = "demo@puregamma.ai"
    name: str = "Demo User"
    locale: str = "en"


class LocalePreferenceRequest(BaseModel):
    locale: str


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
        "email_verified": bool(user.email_verified_at),
        "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "login_methods": sorted({identity.provider for identity in user.identities} | {user.auth_provider}),
        "locale": user.preference.locale if user.preference else "en",
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }


@router.post("/auth/mock-login")
def mock_login(payload: MockLoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if not user:
        user = User(email=payload.email, name=payload.name, role="user", plan="Free", credit_balance=30, auth_provider="mock")
        db.add(user)
        db.flush()
    user.auth_provider = user.auth_provider or "mock"
    user.name = payload.name
    if user.email != "demo@puregamma.ai":
        user.role = "user"
    locale = normalize_locale(payload.locale)
    if not user.preference:
        db.add(UserPreference(user_id=user.id, email_recipient=user.email, imessage_recipient="+15555550100", locale=locale))
    else:
        user.preference.locale = locale
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)
    token = set_session_cookie(response, user)
    return {"user": serialize_user(user), "access_token": token, "token_type": "bearer", "auth_header": {"Authorization": f"Bearer {token}"}}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"user": serialize_user(user)}


@router.post("/auth/logout")
def logout(response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/auth/preferences/locale")
def save_locale(payload: LocalePreferenceRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    locale = normalize_locale(payload.locale)
    if not user.preference:
        db.add(UserPreference(user_id=user.id, email_recipient=user.email, imessage_recipient="+15555550100", locale=locale))
    else:
        user.preference.locale = locale
    db.commit()
    db.refresh(user)
    return {"locale": locale, "user": serialize_user(user)}
