from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from packages.data.base import AssetType, MarketQuote, ProviderSource

logger = logging.getLogger(__name__)

FMP_API_BASE = os.getenv("FMP_API_BASE", "https://financialmodelingprep.com/api/v3")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")

EQUITY_ASSET_TYPE_MAP: dict[str, AssetType] = {
    "MSTR": "equity",
    "STRC": "preferred_equity",
    "STRD": "preferred_equity",
    "STRK": "preferred_equity",
    "STRF": "preferred_equity",
}


class FMPProvider:
    provider_name: ProviderSource = "fmp"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or FMP_API_KEY
        self._session = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def get_quote(self, symbol: str) -> MarketQuote | None:
        if not self.enabled:
            return None
        normalized = symbol.upper()
        asset_type = EQUITY_ASSET_TYPE_MAP.get(normalized, "equity")
        try:
            client = self._client()
            resp = client.get(
                f"{FMP_API_BASE}/quote/{normalized}",
                params={"apikey": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data or not isinstance(data, list):
                return None
            quote_data = data[0]

            price = float(quote_data.get("price") or 0)
            change_pct = float(quote_data.get("changesPercentage") or 0)
            volume_shares = float(quote_data.get("volume") or 0)
            market_cap = float(quote_data.get("marketCap") or 0)
            volume_usd = volume_shares * price if volume_shares and price else 0

            return MarketQuote(
                symbol=normalized,
                price=price,
                volume_24h=volume_usd,
                market_cap=market_cap,
                funding_rate=0.0,
                open_interest=0.0,
                volatility=0.0,
                liquidation_estimate=0.0,
                sentiment_score=0.5,
                timestamp=datetime.now(timezone.utc),
                source="fmp",
                source_symbol=f"NASDAQ:{normalized}",
                change_24h=round(change_pct, 2) if change_pct else None,
                is_realtime=True,
                asset_type=asset_type,
                open_interest_usd=None,
            )
        except Exception as exc:
            logger.warning("FMP: failed to fetch %s: %s", normalized, exc)
            return None

    def get_batch_quotes(self, symbols: list[str]) -> dict[str, MarketQuote]:
        result: dict[str, MarketQuote] = {}
        for symbol in symbols:
            quote = self.get_quote(symbol)
            if quote:
                result[symbol.upper()] = quote
        return result
