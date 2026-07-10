from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Generator

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from packages.database.models import User
from packages.database.seed import seed_all
from packages.database.session import SessionLocal, init_db


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
        secure=settings.app_environment == "production",
        samesite="lax",
        path="/",
    )
    return token


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(get_settings().session_cookie_name, path="/")


def require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
