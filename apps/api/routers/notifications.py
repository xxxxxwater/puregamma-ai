from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.i18n import resolve_locale
from apps.api.services.notification_service import send_notification, serialize_delivery
from apps.api.services.daily_push_service import delivery_history, get_or_create_preference, serialize_preference, update_preference
from apps.api.services.imessage_verification_service import VerificationRateLimitError, confirm_verification, request_verification
from apps.api.services.push_device_service import register_device, serialize_device, unregister_device
from apps.api.config import get_settings
from packages.database.models import PushDevice, User, utcnow


router = APIRouter(prefix="/notifications", tags=["notifications"])


class SendNotificationRequest(BaseModel):
    channel: Literal["telegram", "slack", "email", "imessage", "push"] = "email"
    message: str = "PureGamma AI test notification."
    metadata: dict = {}
    locale: str | None = None


class DailyBriefPreferenceRequest(BaseModel):
    enabled: bool | None = None
    timezone: str | None = None
    local_time: str | None = None
    channel: str | None = None
    channels: list[str] | None = None
    report_types: list[str] | None = None
    locale: str | None = None
    include_portfolio: bool | None = None
    include_market: bool | None = None
    include_signals: bool | None = None
    include_risk: bool | None = None
    include_sentiment: bool | None = None
    quiet_hours: dict | None = None
    max_length: int | None = None


class IMessageVerifyRequest(BaseModel):
    recipient: str


class IMessageVerifyConfirm(BaseModel):
    challenge_id: str
    code: str


class PushDeviceRequest(BaseModel):
    token: str = Field(min_length=64, max_length=256)
    environment: str = "production"
    locale: str = "en"
    timezone: str = "UTC"


@router.get("/devices")
def push_devices(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.query(PushDevice).filter_by(user_id=user.id, enabled=True).order_by(PushDevice.last_seen_at.desc()).all()
    return {"devices": [serialize_device(row) for row in rows], "delivery_available": get_settings().apns_enabled}


@router.post("/devices")
def put_push_device(payload: PushDeviceRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = register_device(db, user, token=payload.token, environment=payload.environment, locale=payload.locale, timezone_name=payload.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc)}) from exc
    return {"device": serialize_device(row), "delivery_available": get_settings().apns_enabled}


@router.post("/devices/unregister")
def remove_push_device(payload: PushDeviceRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        removed = unregister_device(db, user, payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc)}) from exc
    return {"ok": True, "removed": removed}


@router.get("/imessage/config")
def imessage_config(user: User = Depends(get_current_user)) -> dict:
    settings = get_settings()
    preference = getattr(user, "preference", None)
    verified_at = getattr(preference, "imessage_recipient_verified_at", None)
    return {
        "official_number": settings.imessage_official_number,
        "provider": settings.imessage_provider,
        "enabled_plans": list(settings.imessage_enabled_plans),
        "recipient": getattr(preference, "imessage_recipient", None),
        "recipient_verified_at": verified_at.isoformat() if verified_at else None,
    }


@router.post("/imessage/verify/request")
def request_imessage_verification(payload: IMessageVerifyRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return request_verification(db, user, payload.recipient)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc)}) from exc
    except VerificationRateLimitError as exc:
        raise HTTPException(status_code=429, detail={"code": str(exc)}, headers={"Retry-After": "3600"}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail={"code": str(exc)}) from exc


@router.post("/imessage/verify/confirm")
def confirm_imessage_verification(payload: IMessageVerifyConfirm, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        return confirm_verification(db, user, payload.challenge_id, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc)}) from exc


@router.post("/imessage/test")
def test_imessage(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    message = "PureGamma AI iMessage test."
    delivery = send_notification(db, user.id, "imessage", message, {"idempotency_key": f"imessage-test:{user.id}:{utcnow().isoformat()}", "locale": getattr(user.preference, "locale", "en")})
    return {"delivery": serialize_delivery(delivery)}


@router.get("/preferences/daily-brief")
def daily_brief_preference(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = get_or_create_preference(db, user)
    history = delivery_history(db, user.id, row.channel)
    return {"preference": serialize_preference(row), "history": [serialize_delivery(item) for item in history]}


@router.put("/preferences/daily-brief")
def put_daily_brief_preference(payload: DailyBriefPreferenceRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    try:
        row = update_preference(db, user, payload.model_dump(exclude_none=True))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"code": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc)}) from exc
    return {"preference": serialize_preference(row)}


@router.post("/test")
def test_notification(
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    language = resolve_locale(query_locale=locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    message = "PureGamma AI 测试通知。" if language == "zh" else "PureGamma AI test notification."
    delivery = send_notification(db, user.id, "email", message, {"idempotency_key": f"test-{user.id}-{language}", "locale": language})
    return {"delivery": serialize_delivery(delivery)}


@router.post("/send")
def send(
    payload: SendNotificationRequest,
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    language = resolve_locale(query_locale=payload.locale or locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    metadata = {**payload.metadata, "locale": language}
    delivery = send_notification(db, user.id, payload.channel, payload.message, metadata)
    return {"delivery": serialize_delivery(delivery)}


@router.get("/deliveries")
def deliveries(channel: str | None = Query(default=None), db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = delivery_history(db, user.id, channel)
    return {"deliveries": [serialize_delivery(row) for row in rows]}
