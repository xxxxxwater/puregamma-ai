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
    message: str = "PureGamma.ai test notification. This is not financial advice."
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
    message = "PureGamma.ai 测试通知。本内容仅供信息和研究参考，不构成投资建议。" if language == "zh" else "PureGamma.ai test notification. This is not financial advice."
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
