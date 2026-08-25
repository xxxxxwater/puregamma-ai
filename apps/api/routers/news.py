from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from apps.api.dependencies import get_current_user, get_db
from apps.api.i18n import normalize_locale
from apps.api.services.entitlement_service import get_user_entitlement
from apps.api.services.news_feed_service import list_news_feed
from packages.database.models import User


router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
def news_feed(
    response: Response,
    kind: Literal["all", "flash", "article"] = Query(default="flash"),
    source: Literal["all", "chaincatcher", "rss"] = Query(default="chaincatcher"),
    language: str | None = Query(default=None, max_length=10),
    symbol: str | None = Query(default=None, min_length=1, max_length=12, pattern=r"^[A-Za-z0-9.-]+$"),
    q: str | None = Query(default=None, max_length=100),
    hours: int = Query(default=72, ge=1, le=168),
    limit: int = Query(default=30, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=512),
    x_pg_locale: str | None = Header(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    entitlement = get_user_entitlement(db, user.id)
    allowed = set(entitlement.get("allowed_data_sources") or [])
    if "all" not in allowed and "rss" not in allowed:
        raise HTTPException(status_code=403, detail={"code": "NEWS_SOURCE_NOT_ENTITLED"})
    effective_language = language or normalize_locale(x_pg_locale or getattr(user.preference, "locale", None))
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=45"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return list_news_feed(
        db,
        kind=kind,
        source=source,
        language=effective_language,
        symbol=symbol,
        query_text=q,
        hours=hours,
        limit=limit,
        cursor=cursor,
    )
