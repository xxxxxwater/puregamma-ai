from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.i18n import resolve_locale
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.cost_control_service import DailyLimitExceededError
from apps.api.services.entitlement_service import EntitlementDeniedError
from apps.api.services.report_service import create_daily_report, create_event_report, serialize_report
from apps.api.services.skill_service import begin_module_skill_invocation, finish_module_skill_invocation
from packages.billing.credits import cost_for
from packages.database.models import Report, User
from packages.skills.registry import SkillResolutionError


router = APIRouter(prefix="/reports", tags=["reports"])


class EventReportRequest(BaseModel):
    asset: str
    event: str
    skill_refs: list[dict] = Field(default_factory=list, max_length=8)


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
    invocation_id = None
    try:
        invocation_id, _ = begin_module_skill_invocation(
            db,
            user,
            payload.skill_refs,
            trigger_source="report",
            input_payload={"query": f"{payload.asset}: {payload.event}", "asset": payload.asset, "event": payload.event, "language": language},
            estimated_credits=cost_for("event_report"),
        )
        db.commit()
        report = create_event_report(db, user.id, payload.asset, payload.event, language)
        finish_module_skill_invocation(db, invocation_id, status="completed", credits_used=cost_for("event_report"), output_summary=report.title, evidence={"report_id": report.id})
        db.commit()
        return {"report": serialize_report(report)}
    except SkillResolutionError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        db.rollback()
        if invocation_id:
            finish_module_skill_invocation(db, invocation_id, status="failed", credits_used=0, error_code="REPORT_REJECTED")
            db.commit()
        raise HTTPException(status_code=402, detail=str(exc)) from exc


@router.get("")
def list_reports(
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    language = resolve_locale(query_locale=locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    rows = db.query(Report).filter(Report.user_id == user.id, Report.language == language).order_by(Report.created_at.desc()).limit(100).all()
    return {"reports": [serialize_report(row) for row in rows]}


@router.get("/{report_id}")
def get_report(
    report_id: str,
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    language = resolve_locale(query_locale=locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    row = db.get(Report, report_id)
    if not row or row.user_id != user.id or row.language != language:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"report": serialize_report(row)}
