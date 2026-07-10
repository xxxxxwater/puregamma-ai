from __future__ import annotations

from packages.data.base import MarketQuote
from packages.data.mock_provider import MockMarketDataProvider
from packages.risk.scoring import portfolio_risk_summary, risk_score_for_quote


def test_risk_score_is_bounded():
    quote = MockMarketDataProvider().get_snapshot(["HYPE"])[0]

    assert 0 <= risk_score_for_quote(quote) <= 100


def test_risk_score_increases_with_volatility_and_funding():
    low, high = MockMarketDataProvider().get_snapshot(["BTC", "HYPE"])

    assert risk_score_for_quote(high) > risk_score_for_quote(low)


def test_portfolio_risk_summary_labels_moderate_high_risk():
    quote = MarketQuote(
        symbol="HYPE",
        price=40,
        volume_24h=100,
        market_cap=1000,
        funding_rate=0.05,
        open_interest=1000,
        volatility=1.0,
        liquidation_estimate=0,
        sentiment_score=0.9,
        timestamp=MockMarketDataProvider().get_snapshot(["BTC"])[0].timestamp,
    )

    assert risk_score_for_quote(quote) >= 50
    assert "Moderate risk" in portfolio_risk_summary([quote])
