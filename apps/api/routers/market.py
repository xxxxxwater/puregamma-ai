from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db
from apps.api.services.market_intelligence_service import (
    DEFAULT_ASSETS,
    generate_shared_market_intelligence,
    latest_or_create_intelligence,
)
from apps.api.services.data_source_service import data_capability
from packages.data.cache import market_cache
from packages.data.base import MarketQuote, asset_type_for, is_equity
from packages.data.equity_providers.equity_provider import equity_source_label
from packages.data.public_market_provider import PublicMarketDataProvider
from packages.risk.scoring import risk_score_for_quote
from packages.database.models import DataSource, User


router = APIRouter(prefix="/market", tags=["market"])


@router.get("/data-capabilities")
def data_capabilities(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.query(DataSource).order_by(DataSource.category, DataSource.name).all()
    return {"capabilities": [data_capability(db, row, user.id) for row in rows]}


@router.get("/snapshot")
def snapshot() -> dict:
    settings = get_settings()
    mode = (
        "auto"
        if settings.app_environment.lower() == "production"
        and settings.market_data_mode == "mock"
        else settings.market_data_mode
    )
    cached = market_cache.get(f"api:market:snapshot:{mode}")
    if cached:
        return cached
    quotes = PublicMarketDataProvider(mode=mode).get_snapshot(DEFAULT_ASSETS)
    live_count = sum(1 for quote in quotes if quote.is_realtime)
    payload = {
        "mockMode": live_count == 0,
        "live_assets": live_count,
        "source_summary": sorted({quote.source for quote in quotes}),
        "assets": [_serialize_quote(quote) for quote in quotes],
    }
    market_cache.set(
        f"api:market:snapshot:{mode}",
        payload,
        ttl_seconds=settings.market_snapshot_cache_ttl_seconds,
    )
    return payload


def _serialize_quote(quote: MarketQuote) -> dict:
    symbol = quote.symbol
    asset_type = quote.asset_type if quote.asset_type else asset_type_for(symbol)

    if is_equity(symbol):
        source_display = equity_source_label(symbol, quote.source)
    else:
        source_display = quote.source.upper()

    open_interest_val: float | None = None
    if is_equity(symbol):
        open_interest_val = quote.open_interest_usd
    elif quote.open_interest > 0:
        open_interest_val = quote.open_interest

    return {
        "symbol": symbol,
        "price": quote.price,
        "volume_24h": quote.volume_24h,
        "market_cap": quote.market_cap,
        "funding_rate": quote.funding_rate,
        "open_interest": open_interest_val,
        "volatility": quote.volatility,
        "liquidation_estimate": quote.liquidation_estimate,
        "sentiment_score": quote.sentiment_score,
        "risk_score": risk_score_for_quote(quote),
        "change_24h": quote.change_24h,
        "timestamp": quote.timestamp.isoformat(),
        "source": quote.source,
        "source_display": source_display,
        "source_symbol": quote.source_symbol,
        "is_realtime": quote.is_realtime,
        "fallback_reason": quote.fallback_reason,
        "asset_type": asset_type,
        "is_mock": quote.source == "mock",
    }


@router.get("/intelligence")
def intelligence(db: Session = Depends(get_db)) -> dict:
    item = latest_or_create_intelligence(db)
    return {
        "id": item.id,
        "market_regime": item.market_regime,
        "summary_markdown": item.summary_markdown,
        "assets": item.assets,
        "source_snapshot_ids": item.source_snapshot_ids,
        "created_at": item.created_at.isoformat(),
    }


@router.post("/intelligence")
def regenerate_intelligence(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    item = generate_shared_market_intelligence(db)
    return {
        "id": item.id,
        "market_regime": item.market_regime,
        "summary_markdown": item.summary_markdown,
    }
