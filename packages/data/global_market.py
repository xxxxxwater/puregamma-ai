from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from packages.data.base import MarketQuote
from packages.data.yahoo_provider import YahooFinanceProvider

logger = logging.getLogger(__name__)

# NASDAQ liquidity pool; the top 5 by traded volume are surfaced each refresh.
NASDAQ_VOLUME_POOL = [
    "AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "META", "GOOGL", "AVGO", "PLTR", "NFLX", "AMD", "SMCI",
]
PRECIOUS_METALS = ["GC=F", "SI=F"]
FOREX_PAIRS = ["EURUSD=X", "USDJPY=X", "GBPUSD=X", "AUDUSD=X"]
ENERGY = ["CL=F", "BZ=F", "NG=F"]

GROUP_ORDER = ("nasdaq_top", "metals", "forex", "energy")


def _quote_dict(quote: MarketQuote) -> dict[str, Any]:
    return {
        "symbol": quote.symbol,
        "price": quote.price,
        "volume_24h": quote.volume_24h,
        "change_24h": quote.change_24h,
        "timestamp": quote.timestamp.isoformat(),
        "source": quote.source,
        "is_realtime": quote.is_realtime,
        "asset_type": quote.asset_type,
    }


def build_global_snapshot(
    nasdaq_top_n: int = 5,
    provider: YahooFinanceProvider | None = None,
) -> dict[str, Any]:
    """Assemble the cross-market terminal feed.

    NASDAQ equities are ranked by daily traded volume (top N), then the
    metals / FX / energy groups are appended in a fixed order. Any symbol that
    fails to resolve is omitted so one bad feed cannot take the terminal down.
    """
    source = provider or YahooFinanceProvider()
    quotes: list[MarketQuote] = []
    nasdaq = source.get_snapshot(NASDAQ_VOLUME_POOL)
    nasdaq.sort(key=lambda quote: quote.volume_24h, reverse=True)
    top = nasdaq[: max(1, min(nasdaq_top_n, len(NASDAQ_VOLUME_POOL)))]
    quotes.extend(top)

    groups: dict[str, list[dict[str, Any]]] = {
        "nasdaq_top": [_quote_dict(quote) for quote in top],
    }
    for group, symbols in (
        ("metals", PRECIOUS_METALS),
        ("forex", FOREX_PAIRS),
        ("energy", ENERGY),
    ):
        group_quotes = source.get_snapshot(symbols)
        quotes.extend(group_quotes)
        groups[group] = [_quote_dict(quote) for quote in group_quotes]

    return {
        "status": "HEALTHY" if quotes else "DEGRADED",
        "provider": source.provider_name,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "groups": groups,
        "order": list(GROUP_ORDER),
        "live_trading": False,
    }
