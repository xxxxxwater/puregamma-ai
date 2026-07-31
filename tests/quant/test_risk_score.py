from __future__ import annotations

from datetime import datetime, timedelta, timezone

from packages.data.base import MarketQuote
from packages.risk.scoring import data_quality_risk, risk_score_breakdown_for_quote, risk_score_for_quote


def quote(**overrides) -> MarketQuote:
    base = {
        "symbol": "BTC",
        "price": 100000.0,
        "volume_24h": 40_000_000_000.0,
        "market_cap": 2_000_000_000_000.0,
        "funding_rate": 0.002,
        "open_interest": 12_000_000_000.0,
        "volatility": 0.35,
        "liquidation_estimate": 500_000_000.0,
        "sentiment_score": 0.6,
        "timestamp": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return MarketQuote(**base)


def test_high_funding_rate_increases_risk_score():
    normal = risk_score_for_quote(quote(funding_rate=0.002))
    crowded = risk_score_for_quote(quote(funding_rate=0.03))
    assert crowded > normal


def test_stale_price_increases_data_quality_risk():
    as_of = datetime.now(timezone.utc)
    fresh = quote(timestamp=as_of - timedelta(minutes=1))
    stale = quote(timestamp=as_of - timedelta(hours=2))
    assert data_quality_risk(stale, as_of=as_of) > data_quality_risk(fresh, as_of=as_of)


def test_risk_score_breakdown_uses_expected_bucket_names():
    breakdown = risk_score_breakdown_for_quote(quote(funding_rate=0.03, volatility=0.9))
    assert breakdown.total >= 61
    assert breakdown.bucket in {"risk_low", "risk_medium", "risk_high", "risk_extreme"}
    assert breakdown.funding_rate > 0
    assert breakdown.realized_volatility > 0
