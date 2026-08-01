from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.services.options_service import get_option_chain
from packages.options.long_gamma import discover_long_gamma
from packages.options.earnings_gamma import get_earnings_candidates, refresh_earnings_candidates
from packages.options.surface import SURFACE_TYPES, build_surface, compute_atm_snapshot
from packages.options.tickers import surface_tickers

router = APIRouter(prefix="/options", tags=["options"])


def _chain(currency: str) -> dict:
    return get_option_chain(currency)


@router.get("/chain")
def option_chain(
    currency: str = Query(default="BTC"),
) -> dict:
    return _chain(currency)


@router.get("/long-gamma")
def long_gamma(
    currency: str = Query(default="BTC"),
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


@router.get("/surface")
def option_surface(
    currency: str = Query(default="BTC"),
    type: str = Query(default="mark_iv"),
) -> dict:
    chain = _chain(currency)
    instruments = chain["instruments"]
    if not instruments:
        return {
            "status": chain["status"],
            "provider": chain["provider"],
            "currency": chain["currency"],
            "surface": {"x": [], "y": [], "z": [], "type": type, "underlying_price": 0, "rows": []},
            "candidates": [],
            "insights": None,
            "error": chain.get("error"),
            "live_trading": False,
        }
    surface = build_surface(chain, type)
    candidates = discover_long_gamma(instruments, limit=8)
    return {
        "status": chain["status"],
        "provider": chain["provider"],
        "currency": chain["currency"],
        "fetched_at": chain.get("fetched_at"),
        "surface": surface,
        "candidates": candidates,
        "insights": compute_atm_snapshot(surface),
        "error": chain.get("error"),
        "live_trading": False,
    }


@router.get("/surface-tickers")
def surface_tickers_endpoint() -> dict:
    return {"tickers": surface_tickers()}


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
