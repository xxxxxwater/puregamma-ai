from __future__ import annotations

from datetime import datetime, timezone

from packages.data.base import MarketDataProvider, MarketQuote, asset_type_for


BASE: dict[str, tuple] = {
    "BTC": (108500.0, 42_000_000_000, 2_130_000_000_000, 0.006, 18_900_000_000, 0.42, 850_000_000, 0.62),
    "ETH": (5850.0, 18_000_000_000, 705_000_000_000, 0.004, 9_600_000_000, 0.48, 410_000_000, 0.58),
    "SOL": (228.0, 7_400_000_000, 117_000_000_000, 0.012, 3_800_000_000, 0.72, 220_000_000, 0.66),
    "HYPE": (39.2, 1_200_000_000, 13_400_000_000, 0.018, 990_000_000, 0.83, 95_000_000, 0.71),
    "MSTR": (1840.0, 2_100_000_000, 48_000_000_000, 0.0, 0.0, 0.68, 0.0, 0.55),
    "STRC": (101.8, 140_000_000, 7_800_000_000, 0.0, 0.0, 0.22, 0.0, 0.49),
    "STRD": (75.0, 80_000_000, 3_500_000_000, 0.0, 0.0, 0.30, 0.0, 0.45),
    "STRK": (60.0, 50_000_000, 2_800_000_000, 0.0, 0.0, 0.28, 0.0, 0.42),
    "STRF": (55.0, 40_000_000, 2_200_000_000, 0.0, 0.0, 0.25, 0.0, 0.40),
}


class MockMarketDataProvider(MarketDataProvider):
    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        now = datetime.now(timezone.utc)
        quotes = []
        for index, symbol in enumerate(symbols):
            price, volume, cap, funding, oi, vol, liq, sentiment = BASE.get(symbol, BASE["BTC"])
            drift = 1 + (index * 0.003)
            atype = asset_type_for(symbol)
            is_equity_asset = atype in ("equity", "preferred_equity")
            quotes.append(
                MarketQuote(
                    symbol=symbol,
                    price=round(price * drift, 2),
                    volume_24h=volume,
                    market_cap=cap,
                    funding_rate=0.0 if is_equity_asset else funding,
                    open_interest=0.0 if is_equity_asset else oi,
                    volatility=vol,
                    liquidation_estimate=liq,
                    sentiment_score=sentiment,
                    timestamp=now,
                    source="mock",
                    source_symbol=symbol,
                    change_24h=round((index + 1) * 0.9 - (0.4 if symbol == "STRC" else 0), 2),
                    is_realtime=False,
                    asset_type=atype,
                    open_interest_usd=None if is_equity_asset else oi,
                )
            )
        return quotes

    def get_market_regime(self, quotes: list[MarketQuote]) -> str:
        avg_sentiment = sum(q.sentiment_score for q in quotes) / max(len(quotes), 1)
        avg_funding = sum(q.funding_rate for q in quotes) / max(len(quotes), 1)
        if avg_sentiment > 0.63 and avg_funding < 0.015:
            return "Risk-on momentum with contained leverage"
        if avg_funding > 0.02:
            return "Crowded leverage risk"
        return "Mixed consolidation"
