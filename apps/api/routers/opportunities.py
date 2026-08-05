"""Opportunity surfaces: real-data research dashboards.

Public, read-only. The browser never scrapes upstream sources; all fetching,
normalization and caching happens here.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from apps.api.services import mstr_btc_service

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

_SUPPORTED_LOCALES = {"en", "zh"}


def _locale(request: Request, locale: str | None) -> str:
    candidate = (locale or request.headers.get("x-pg-locale") or "en").lower()
    return candidate if candidate in _SUPPORTED_LOCALES else "en"


@router.get("/mstr-btc")
def mstr_btc_dashboard(request: Request, locale: str | None = None) -> dict:
    """Real-data MSTR/BTC treasury dashboard.

    Every metric carries source URL, as-of timestamp, freshness status and
    methodology; unavailable data is reported explicitly, never fabricated.
    """
    return mstr_btc_service.get_dashboard(_locale(request, locale))
