from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.i18n import resolve_locale
from apps.api.services.notification_service import send_notification, serialize_delivery
from apps.api.services.daily_push_service import delivery_history, get_or_create_preference, serialize_preference, update_preference
from apps.api.services.imessage_verification_service import VerificationRateLimitError, confirm_verification, request_verification
from packages.database.models import User, utcnow


router = APIRouter(prefix="/notifications", tags=["notifications"])


class SendNotificationRequest(BaseModel):
    channel: str = "email"
    message: str = "PureGamma AI test notification. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."
    metadata: dict = {}
    locale: str | None = None


class DailyBriefPreferenceRequest(BaseModel):
    enabled: bool | None = None
    timezone: str | None = None
    local_time: str | None = None
    channel: str | None = None
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
    message = "PureGamma AI iMessage test. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."
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
    message = "PureGamma AI 测试通知。使用该服务用户自行承担风险 提供本服务的主体概不负责AI生成所有责任。" if language == "zh" else "PureGamma AI test notification. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."
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
