from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from packages.agents.research_agent import ResearchAgent
from packages.database.models import MarketSnapshot, SharedMarketIntelligence


# MSTR/STRC removed: no equity market-data key is configured in production, so
# those quotes always failed and never produced real snapshots.
DEFAULT_ASSETS = ["BTC", "ETH", "HYPE"]
# A market conclusion must be based on a recent, complete live snapshot.  A
# five-minute shared window avoids a provider request per user while keeping a
# morning notification or a manually generated report from reusing an old
# market regime.
MARKET_INTELLIGENCE_MAX_AGE = timedelta(minutes=5)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def generate_shared_market_intelligence(db: Session, assets: list[str] | None = None) -> SharedMarketIntelligence:
    assets = assets or DEFAULT_ASSETS
    research = ResearchAgent().research(assets)
    _require_complete_live_quotes(research["quotes"], assets)
    snapshot_ids = []
    for quote in research["quotes"]:
        row = MarketSnapshot(
            asset_id=quote.symbol,
            price=quote.price,
            volume_24h=quote.volume_24h,
            market_cap=quote.market_cap,
            funding_rate=quote.funding_rate,
            open_interest=quote.open_interest,
            timestamp=quote.timestamp,
        )
        db.add(row)
        db.flush()
        snapshot_ids.append(row.id)
    summary = "\n".join(
        [
            f"Market regime: {research['market_regime']}",
            f"Risk: {research['risk_summary']}",
            "Shared intelligence is generated once and reused for user-personalized reports.",
        ]
    )
    intelligence = SharedMarketIntelligence(
        market_regime=research["market_regime"],
        summary_markdown=summary,
        assets=assets,
        source_snapshot_ids=snapshot_ids,
    )
    db.add(intelligence)
    db.commit()
    db.refresh(intelligence)
    return intelligence


def _require_complete_live_quotes(quotes: list, assets: list[str]) -> None:
    """Reject partial or delayed market snapshots in production.

    Persisting a partial response as a new shared-intelligence row makes it
    look current even though one of the headline instruments is missing.  The
    mock provider remains available only for the explicit offline/test mode.
    """
    if os.getenv("ENABLE_MOCK_MARKET_DATA", "false").lower() == "true":
        return
    expected = {asset.upper() for asset in assets}
    by_symbol = {str(quote.symbol).upper(): quote for quote in quotes}
    now = datetime.now(timezone.utc)
    missing = sorted(expected - set(by_symbol))
    delayed = sorted(symbol for symbol in expected if symbol in by_symbol and not bool(by_symbol[symbol].is_realtime))
    invalid_price = sorted(symbol for symbol in expected if symbol in by_symbol and float(by_symbol[symbol].price or 0) <= 0)
    stale = sorted(
        symbol
        for symbol in expected
        if symbol in by_symbol and now - _as_utc(by_symbol[symbol].timestamp) > MARKET_INTELLIGENCE_MAX_AGE
    )
    if missing or delayed or invalid_price or stale:
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if delayed:
            details.append(f"delayed={','.join(delayed)}")
        if invalid_price:
            details.append(f"invalid_price={','.join(invalid_price)}")
        if stale:
            details.append(f"stale={','.join(stale)}")
        raise RuntimeError("LIVE_MARKET_DATA_UNAVAILABLE:" + ";".join(details))


def latest_or_create_intelligence(db: Session) -> SharedMarketIntelligence:
    latest = db.query(SharedMarketIntelligence).order_by(SharedMarketIntelligence.created_at.desc()).first()
    return latest or generate_shared_market_intelligence(db)


def fresh_or_create_intelligence(
    db: Session,
    *,
    max_age: timedelta = MARKET_INTELLIGENCE_MAX_AGE,
) -> SharedMarketIntelligence:
    """Return shared intelligence only when it was rebuilt recently.

    Daily reports must never silently turn an hours- or days-old research row
    into a "current" market view.  The first brief after the short freshness
    window refreshes the shared live snapshot; a provider failure bubbles up
    so the caller can withhold the report rather than publish stale prices.
    """
    latest = db.query(SharedMarketIntelligence).order_by(SharedMarketIntelligence.created_at.desc()).first()
    if latest and datetime.now(timezone.utc) - _as_utc(latest.created_at) <= max_age:
        return latest
    return generate_shared_market_intelligence(db)
