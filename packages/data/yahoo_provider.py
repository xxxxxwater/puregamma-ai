from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from packages.data.base import AssetType, MarketQuote

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Asset-type classification for non-crypto global markets.
ASSET_TYPE_MAP: dict[str, AssetType] = {
    "GC=F": "commodity",
    "SI=F": "commodity",
    "CL=F": "commodity",
    "BZ=F": "commodity",
    "NG=F": "commodity",
    "HG=F": "commodity",
    "XAUUSD=X": "commodity",
    "EURUSD=X": "forex",
    "USDJPY=X": "forex",
    "GBPUSD=X": "forex",
    "AUDUSD=X": "forex",
    "USDCNH=X": "forex",
}

EQUITY_LABEL_OVERRIDES: dict[str, str] = {}


class YahooFinanceProvider:
    """Keyless Yahoo Finance quote provider for global markets.

    Serves NASDAQ equities, metals, FX pairs, and energy futures through the
    public chart endpoint. Every quote carries is_realtime=False because the
    feed is delayed; timestamps come from the exchange session.
    """

    provider_name = "yahoo_finance"

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    def get_quote(self, symbol: str) -> MarketQuote | None:
        normalized = symbol.upper()
        try:
            payload = self._chart(normalized)
        except Exception as exc:
            logger.warning("Yahoo: failed to fetch %s: %s", normalized, str(exc)[:160])
            return None
        result = (payload.get("chart", {}).get("result") or [{}])[0]
        meta = result.get("meta", {}) or {}
        price = meta.get("regularMarketPrice")
        if price is None:
            return None
        previous = meta.get("chartPreviousClose") or meta.get("previousClose") or price
        change_pct = ((float(price) - float(previous)) / float(previous) * 100) if previous else None
        volume = float(meta.get("regularMarketVolume") or 0)
        timestamp = datetime.fromtimestamp(float(meta.get("regularMarketTime") or 0), timezone.utc)
        return MarketQuote(
            symbol=normalized,
            price=float(price),
            volume_24h=volume * float(price) if volume else 0.0,
            market_cap=0.0,
            funding_rate=0.0,
            open_interest=0.0,
            volatility=0.0,
            liquidation_estimate=0.0,
            sentiment_score=0.5,
            timestamp=timestamp,
            source=self.provider_name,
            source_symbol=normalized,
            change_24h=round(change_pct, 2) if change_pct is not None else None,
            is_realtime=False,
            asset_type=ASSET_TYPE_MAP.get(normalized, "equity"),
            open_interest_usd=None,
        )

    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        return [quote for symbol in symbols if (quote := self.get_quote(symbol))]

    def _chart(self, symbol: str) -> dict[str, Any]:
        response = httpx.get(
            YAHOO_CHART_URL.format(symbol=symbol),
            params={"interval": "1d", "range": "5d"},
            timeout=self.timeout,
            headers={"User-Agent": "Mozilla/5.0 (PureGamma AI market terminal)"},
        )
        response.raise_for_status()
        return response.json()
