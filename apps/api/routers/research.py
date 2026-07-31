"""Unified research facts API: daily answers, impacts, events, opportunities.

Read-only. Facts come from the stored research pipeline; unavailable sources
surface as degraded health with empty lists, never placeholder content.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, Query
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.i18n import resolve_locale
from apps.api.services import research_event_service
from packages.database.models import User

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/today")
def research_today(
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    language = resolve_locale(query_locale=locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    return research_event_service.get_today(db, user, language)


@router.get("/overnight")
def research_overnight(
    since_hours: int = Query(default=14, ge=1, le=72),
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    resolve_locale(query_locale=locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    return research_event_service.get_overnight(db, user, since_hours)


@router.get("/portfolio/impact")
def research_portfolio_impact(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return research_event_service.get_portfolio_impact(db, user)


@router.get("/events/upcoming")
def research_upcoming_events(
    days: int = Query(default=14, ge=1, le=60),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return research_event_service.get_upcoming_events(db, days)


@router.get("/opportunities")
def research_opportunities(
    locale: str | None = Query(default=None),
    x_pg_locale: str | None = Header(default=None),
    pg_locale: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    language = resolve_locale(query_locale=locale, header_locale=x_pg_locale, user=user, cookie_locale=pg_locale)
    return research_event_service.get_opportunities(db, user, language)


@router.get("/alerts")
def research_alerts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return research_event_service.get_alerts(db, user)
