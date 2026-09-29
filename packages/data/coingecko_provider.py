from __future__ import annotations

from packages.data.base import MarketDataProvider, MarketQuote
from packages.data.provider import ProviderError


class CoinGeckoProvider(MarketDataProvider):
    """Compatibility facade that refuses to fabricate quotes."""

    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        raise ProviderError(
            "provider_unavailable",
            "CoinGecko is not connected to the reviewed production provider registry",
        )

    def get_market_regime(self, quotes: list[MarketQuote]) -> str:
        raise ProviderError(
            "provider_unavailable",
            "CoinGecko regime analysis requires reviewed live market data",
        )
