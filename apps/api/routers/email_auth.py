from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import (
    get_current_user,
    get_db,
    set_session_cookie,
)
from apps.api.config import get_settings
from apps.api.i18n import normalize_locale
from apps.api.routers.auth import serialize_user
from apps.api.routers.captcha import CaptchaError, verify_captcha
from packages.database.models import User, UserPreference
from packages.security.passwords import hash_password, verify_password
from packages.notifications.email import send_email

router = APIRouter(tags=["email-auth"])
logger = logging.getLogger("puregamma.email_auth")


def _token_digest(token: str) -> str:
    """Store only the SHA-256 digest of one-time tokens; plaintext never persists."""
    return hashlib.sha256(token.encode()).hexdigest()

_COMMON_PASSWORDS = frozenset({
    "password", "password1", "password12", "password123",
    "12345678", "123456789", "1234567890",
    "qwertyuiop", "asdfghjkl", "zxcvbnm",
    "iloveyou", "sunshine", "trustno1",
    "puregamma", "puregamma1", "puregammaai",
})

_MIN_PASSWORD_LENGTH = 8


class EmailRegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128)
    name: str = Field(min_length=1, max_length=120, default="")
    locale: str = Field(default="en", max_length=5)
    captcha_id: str | None = Field(default=None, max_length=64)
    captcha_offset: int | None = Field(default=None, ge=0, le=400)


class EmailLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    captcha_id: str | None = Field(default=None, max_length=64)
    captcha_offset: int | None = Field(default=None, ge=0, le=400)


class EmailVerifyRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128)


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$")


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _validate_email_format(email: str) -> None:
    """Reject syntactically invalid or TLD-less addresses (e.g. a@xxx)."""
    if not _EMAIL_RE.match(email) or ".." in email:
        raise HTTPException(status_code=400, detail={"code": "INVALID_EMAIL"})


_PASSWORD_RULE_MESSAGES = {
    "length": "Password must be at least 8 characters",
    "common": "Password is too common",
    "letter": "Password must contain at least one letter",
    "digit": "Password must contain at least one digit",
    "uppercase": "Password must contain at least one uppercase letter",
}


def _check_password_strength(password: str) -> str | None:
    """Return a machine-readable weakness rule code, or None when acceptable."""
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


def _weak_password_error(rule: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "PASSWORD_TOO_WEAK", "rule": rule, "message": _PASSWORD_RULE_MESSAGES[rule]},
    )


def _email_rate_limit(request: Request, email: str, action: str, limit: int = 5, window: int = 900) -> None:
    settings = get_settings()
    if settings.app_environment.lower() != "production":
        return
    forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
    client = forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    fingerprint = hashlib.sha256(f"{client}:{email.lower()}:{action}".encode()).hexdigest()
    key = f"pg:auth:email:{fingerprint}"
    try:
        from apps.api.redis_client import get_redis
        redis = get_redis()
        count = int(redis.incr(key))
        if count == 1:
            redis.expire(key, window)
        if count > limit:
            raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED"}, headers={"Retry-After": str(window)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("email_rate_limit_unavailable", extra={"error": type(exc).__name__})
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc


def _send_verification_email(user: User) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    user.email_verification_token = _token_digest(token)
    user.email_verification_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    verify_url = f"{settings.site_url}/verify-email?token={token}"
    subject = "PureGamma AI - Verify your email / 验证邮箱"
    body = (
        f"Welcome to PureGamma AI!\n\n"
        f"Please click the link below to verify your email address:\n"
        f"{verify_url}\n\n"
        f"This link expires in 24 hours. If you did not create this account, please ignore this email.\n\n"
        f"If you did not receive this email in your inbox, please check your spam folder.\n\n"
        f"---\n\n"
        f"欢迎使用 PureGamma AI！\n\n"
        f"请点击下方链接验证邮箱地址：\n"
        f"{verify_url}\n\n"
        f"链接 24 小时内有效。如非本人操作，请忽略。\n"
        f"若未在收件箱中找到，请检查垃圾邮件箱。"
    )
    if not send_email(recipient=user.email, subject=subject, body=body):
        raise RuntimeError("SMTP not configured")


def _send_password_reset_email(user: User) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    user.password_reset_token = _token_digest(token)
    user.password_reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    reset_url = f"{settings.site_url}/reset-password?token={token}"
    subject = "PureGamma AI - Reset your password / 重置密码"
    body = (
        f"Someone requested a password reset for your PureGamma AI account.\n\n"
        f"Click the link below to set a new password:\n"
        f"{reset_url}\n\n"
        f"This link expires in 1 hour. If you did not request this, please ignore this email.\n\n"
        f"---\n\n"
        f"有人请求重置您的 PureGamma AI 账户密码。\n\n"
        f"点击下方链接设置新密码：\n"
        f"{reset_url}\n\n"
        f"链接 1 小时内有效。如非本人操作，请忽略。"
    )
    if not send_email(recipient=user.email, subject=subject, body=body):
        raise RuntimeError("SMTP not configured")


def _send_password_changed_notice(user: User) -> None:
    """Security notice after any password change; delivery failure never blocks auth."""
    try:
        send_email(
            recipient=user.email,
            subject="PureGamma AI - Your password was changed / 密码已变更",
            body=(
                "Your PureGamma AI account password was just changed.\n"
                "If this was not you, please contact support immediately.\n\n"
                "---\n\n"
                "您的 PureGamma AI 账户密码刚刚被修改。\n"
                "如非本人操作，请立即联系支持团队。"
            ),
        )
    except Exception as exc:
        logger.warning("password_changed_notice_failed", extra={"user_id": user.id, "error": type(exc).__name__})


# ── Registration ─────────────────────────────────────

@router.post("/auth/email/register")
def email_register(
    payload: EmailRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    email = _normalize_email(payload.email)
    _validate_email_format(email)
    try:
        verify_captcha(payload.captcha_id, payload.captcha_offset)
    except CaptchaError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code}) from exc

    _email_rate_limit(request, email, "register", limit=3, window=900)

    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail={"code": "EMAIL_ALREADY_REGISTERED"})

    weakness = _check_password_strength(payload.password)
    if weakness:
        raise _weak_password_error(weakness)

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
    )
    db.add(user)
    db.flush()

    if not user.preference:
        db.add(UserPreference(user_id=user.id, email_recipient=email, locale=locale))

    email_sent = False
    try:
        _send_verification_email(user)
        email_sent = True
    except Exception as exc:
        logger.warning("email_verification_send_failed", extra={"user_id": user.id, "error": type(exc).__name__})

    db.commit()
    db.refresh(user)
    logger.info("email_register_succeeded", extra={"user_id": user.id})
    return {
        "user": serialize_user(user),
        "message": "Verification email sent" if email_sent else "Account created but verification email could not be sent",
        "email_sent": email_sent,
    }


# ── Login ────────────────────────────────────────────

@router.post("/auth/email/login")
def email_login(
    payload: EmailLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    email = _normalize_email(payload.email)
    _validate_email_format(email)
    try:
        verify_captcha(payload.captcha_id, payload.captcha_offset)
    except CaptchaError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code}) from exc
    _email_rate_limit(request, email, "login", limit=5, window=900)
    user = db.query(User).filter(User.email == email, User.password_hash.isnot(None)).one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS"})

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS"})

    if not user.email_verified_at:
        raise HTTPException(status_code=403, detail={"code": "EMAIL_NOT_VERIFIED", "email": email})

    user.last_login_at = datetime.now(timezone.utc)
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)
    set_session_cookie(response, user)

    logger.info("email_login_succeeded", extra={"user_id": user.id})
    return {"user": serialize_user(user)}


# ── Verification ─────────────────────────────────────

@router.post("/auth/email/verify")
def email_verify(
    payload: EmailVerifyRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    token = payload.token.strip()
    user = db.query(User).filter(
        User.email_verification_token == _token_digest(token),
        User.email_verification_token_expires_at > datetime.now(timezone.utc)
    ).one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail={"code": "INVALID_OR_EXPIRED_TOKEN"})

    user.email_verified_at = datetime.now(timezone.utc)
    user.email_verification_token = None
    user.email_verification_token_expires_at = None
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)
    set_session_cookie(response, user)

    logger.info("email_verified", extra={"user_id": user.id})
    return {"user": serialize_user(user), "message": "Email verified"}


@router.post("/auth/email/resend-verification")
def email_resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    email = _normalize_email(payload.email)
    _email_rate_limit(request, email, "resend", limit=3, window=900)

    user = db.query(User).filter(User.email == email).one_or_none()
    if not user:
        logger.info("email_resend_verification_no_user", extra={"email": email})
        return {"message": "If an account with this email exists and is not yet verified, a verification email has been sent."}

    if user.email_verified_at:
        return {"message": "If an account with this email exists and is not yet verified, a verification email has been sent."}

    try:
        _send_verification_email(user)
    except Exception as exc:
        logger.error("email_verification_resend_failed", extra={"user_id": user.id, "error": type(exc).__name__})
        return {"message": "If an account with this email exists and is not yet verified, a verification email has been sent."}

    db.commit()
    return {"message": "If an account with this email exists and is not yet verified, a verification email has been sent."}


# ── Forgot / Reset Password ──────────────────────────

@router.post("/auth/email/forgot-password")
def email_forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    email = _normalize_email(payload.email)
    _email_rate_limit(request, email, "forgot", limit=2, window=900)

    user = db.query(User).filter(User.email == email, User.password_hash.isnot(None)).one_or_none()
    if user:
        try:
            _send_password_reset_email(user)
            db.commit()
        except Exception as exc:
            logger.error("password_reset_send_failed", extra={"user_id": user.id, "error": type(exc).__name__})

    return {"message": "If an account with that email exists, a password reset link has been sent."}


@router.post("/auth/email/reset-password")
def email_reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    token = payload.token.strip()
    user = db.query(User).filter(
        User.password_reset_token == _token_digest(token),
        User.password_reset_token_expires_at > datetime.now(timezone.utc)
    ).one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail={"code": "INVALID_OR_EXPIRED_TOKEN"})

    weakness = _check_password_strength(payload.password)
    if weakness:
        raise _weak_password_error(weakness)

    user.password_hash = hash_password(payload.password)
    user.password_reset_token = None
    user.password_reset_token_expires_at = None
    user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)
    set_session_cookie(response, user)
    _send_password_changed_notice(user)

    logger.info("password_reset_succeeded", extra={"user_id": user.id})
    return {"user": serialize_user(user), "message": "Password has been reset"}


# ── Change Password ──────────────────────────────────

@router.post("/auth/email/change-password")
def email_change_password(
    payload: ChangePasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not user.password_hash:
        raise HTTPException(status_code=400, detail={"code": "NO_PASSWORD_SET"})

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "INVALID_CURRENT_PASSWORD"})

    weakness = _check_password_strength(payload.new_password)
    if weakness:
        raise _weak_password_error(weakness)

    user.password_hash = hash_password(payload.new_password)
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)
    _send_password_changed_notice(user)

    logger.info("password_changed", extra={"user_id": user.id})
    return {"user": serialize_user(user), "message": "Password changed"}


# ── Set Password (for Google users) ──────────────────

@router.post("/auth/email/set-password")
def email_set_password(
    payload: ChangePasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.password_hash:
        raise HTTPException(status_code=400, detail={"code": "PASSWORD_ALREADY_SET"})

    weakness = _check_password_strength(payload.new_password)
    if weakness:
        raise _weak_password_error(weakness)

    user.password_hash = hash_password(payload.new_password)
    user.session_version = int(user.session_version or 0) + 1
    db.commit()
    db.refresh(user)

    logger.info("password_set", extra={"user_id": user.id})
    return {"user": serialize_user(user), "message": "Password set"}
