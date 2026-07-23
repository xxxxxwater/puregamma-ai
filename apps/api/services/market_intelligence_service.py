from __future__ import annotations

from sqlalchemy.orm import Session

from packages.agents.research_agent import ResearchAgent
from packages.database.models import MarketSnapshot, SharedMarketIntelligence


# MSTR/STRC removed: no equity market-data key is configured in production, so
# those quotes always failed and never produced real snapshots.
DEFAULT_ASSETS = ["BTC", "ETH", "HYPE"]


def generate_shared_market_intelligence(db: Session, assets: list[str] | None = None) -> SharedMarketIntelligence:
    assets = assets or DEFAULT_ASSETS
    research = ResearchAgent().research(assets)
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
            "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.",
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


def latest_or_create_intelligence(db: Session) -> SharedMarketIntelligence:
    latest = db.query(SharedMarketIntelligence).order_by(SharedMarketIntelligence.created_at.desc()).first()
    return latest or generate_shared_market_intelligence(db)
