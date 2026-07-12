from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.i18n import resolve_locale
from apps.api.services.notification_service import send_notification, serialize_delivery
from packages.database.models import NotificationDelivery, User


router = APIRouter(prefix="/notifications", tags=["notifications"])


class SendNotificationRequest(BaseModel):
    channel: str = "email"
    message: str = "PureGamma AI test notification. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."
    metadata: dict = {}
    locale: str | None = None


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
def deliveries(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.user_id == user.id)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(100)
        .all()
    )
    return {"deliveries": [serialize_delivery(row) for row in rows]}
