from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.services.options_service import get_option_chain
from packages.options.long_gamma import discover_long_gamma
from packages.options.earnings_gamma import get_earnings_candidates, refresh_earnings_candidates

router = APIRouter(prefix="/options", tags=["options"])


def _chain(currency: str) -> dict:
    return get_option_chain(currency)


@router.get("/chain")
def option_chain(
    currency: str = Query(default="BTC", pattern="^(BTC|ETH)$"),
) -> dict:
    return _chain(currency)


@router.get("/long-gamma")
def long_gamma(
    currency: str = Query(default="BTC", pattern="^(BTC|ETH)$"),
    limit: int = Query(default=10, ge=1, le=25),
) -> dict:
    chain = _chain(currency)
    return {
        "provider": chain["provider"],
        "status": chain["status"],
        "currency": chain["currency"],
        "fetched_at": chain.get("fetched_at"),
        "source_url": chain.get("source_url"),
        "instrument_count": len(chain["instruments"]),
        "candidates": discover_long_gamma(chain["instruments"], limit),
        "error": chain.get("error"),
        "live_trading": False,
    }


@router.get("/earnings-gamma")
def earnings_gamma(
    language: str = Query(default="en", pattern="^(en|zh)$"),
    db: Session = Depends(get_db),
) -> dict:
    candidates = get_earnings_candidates(language)
    if not candidates:
        candidates = refresh_earnings_candidates(db, language)
    return {
        "status": "HEALTHY",
        "source": "earnings_research",
        "candidates": candidates,
        "live_trading": False,
    }
