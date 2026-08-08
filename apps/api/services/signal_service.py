from __future__ import annotations

from sqlalchemy.orm import Session

from packages.agents.research_agent import ResearchAgent
from packages.database.models import Signal
from packages.risk.scoring import risk_score_for_quote


def scan_signals(db: Session, assets: list[str] | None = None) -> list[Signal]:
    assets = assets or ["BTC", "ETH", "HYPE", "MSTR", "STRC"]
    research = ResearchAgent().research(assets)
    rows = []
    for quote in research["quotes"]:
        direction = "long_watch" if quote.sentiment_score >= 0.55 else "neutral"
        confidence = min(0.9, 0.45 + quote.sentiment_score / 3)
        row = Signal(
            asset=quote.symbol,
            signal_type="market_structure",
            direction=direction,
            confidence=round(confidence, 2),
            risk_score=risk_score_for_quote(quote),
            thesis=f"{quote.symbol} has sentiment {quote.sentiment_score:.2f}, funding {quote.funding_rate:.3%}, and liquidity supports a research watchlist setup.",
            catalyst="Momentum continuation, funding reset, and relative strength confirmation.",
            invalidation="Break below recent range support or funding turns crowded without spot confirmation.",
            timeframe="2-10 days",
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def serialize_signal(signal: Signal) -> dict:
    return {
        "id": signal.id,
        "asset": signal.asset,
        "signal_type": signal.signal_type,
        "direction": signal.direction,
        "confidence": signal.confidence,
        "risk_score": signal.risk_score,
        "thesis": signal.thesis,
        "catalyst": signal.catalyst,
        "invalidation": signal.invalidation,
        "timeframe": signal.timeframe,
        "created_at": signal.created_at.isoformat(),
    }
