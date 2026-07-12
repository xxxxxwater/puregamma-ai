from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.i18n import resolve_locale
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.cost_control_service import DailyLimitExceededError
from apps.api.services.entitlement_service import EntitlementDeniedError
from apps.api.services.report_service import create_daily_report, create_event_report, serialize_report
from packages.database.models import Report, User


router = APIRouter(prefix="/reports", tags=["reports"])


class EventReportRequest(BaseModel):
    asset: str
    event: str


@router.post("/daily")
def daily_report(
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    language = resolve_locale(query_locale=locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    try:
        return {"report": serialize_report(create_daily_report(db, user.id, language))}
    except (InsufficientCreditsError, DailyLimitExceededError, EntitlementDeniedError) as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc


@router.post("/event")
def event_report(
    payload: EventReportRequest,
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    language = resolve_locale(query_locale=locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    try:
        return {"report": serialize_report(create_event_report(db, user.id, payload.asset, payload.event, language))}
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc


@router.get("")
def list_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.query(Report).filter(Report.user_id == user.id).order_by(Report.created_at.desc()).all()
    return {"reports": [serialize_report(row) for row in rows]}


@router.get("/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.get(Report, report_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"report": serialize_report(row)}
