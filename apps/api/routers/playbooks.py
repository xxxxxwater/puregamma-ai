from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.i18n import resolve_locale
from apps.api.services.credit_service import InsufficientCreditsError
from apps.api.services.entitlement_service import EntitlementDeniedError
from apps.api.services.report_service import create_playbook_report, serialize_report
from packages.database.models import Report, User
from packages.strategies.registry import generate_playbooks


router = APIRouter(prefix="/playbooks", tags=["playbooks"])


@router.post("/generate")
def generate(
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    language = resolve_locale(query_locale=locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    try:
        report = create_playbook_report(db, user.id, language)
        return {"report": serialize_report(report), "playbooks": generate_playbooks()}
    except (InsufficientCreditsError, EntitlementDeniedError) as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc


@router.get("")
def list_playbooks(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.query(Report).filter(Report.user_id == user.id, Report.report_type == "playbook").order_by(Report.created_at.desc()).all()
    return {"playbooks": generate_playbooks(), "reports": [serialize_report(row) for row in rows]}
