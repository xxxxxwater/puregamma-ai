from __future__ import annotations

from packages.data.mock_provider import MockMarketDataProvider


class MarketDataAgent:
    def __init__(self):
        self.provider = MockMarketDataProvider()

    def snapshot(self, assets: list[str]) -> tuple[str, list]:
        quotes = self.provider.get_snapshot(assets)
        return self.provider.get_market_regime(quotes), quotes
