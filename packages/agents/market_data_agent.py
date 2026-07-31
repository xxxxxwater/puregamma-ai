from __future__ import annotations

import os

from packages.data.mock_provider import MockMarketDataProvider
from packages.data.public_market_provider import PublicMarketDataProvider


def _default_provider():
    """Live quotes by default; mock only when explicitly enabled for offline/dev."""
    if os.environ.get("ENABLE_MOCK_MARKET_DATA", "false").lower() == "true":
        return MockMarketDataProvider()
    return PublicMarketDataProvider()


class MarketDataAgent:
    """Market snapshot for shared research.

    Production uses the live public provider chain (Binance -> Coinbase) and
    never silently substitutes mock prices. Tests may inject a stub provider.
    """

    def __init__(self, provider=None):
        self.provider = provider or _default_provider()

    def snapshot(self, assets: list[str]) -> tuple[str, list]:
        quotes = self.provider.get_snapshot(assets)
        return self.provider.get_market_regime(quotes), quotes
