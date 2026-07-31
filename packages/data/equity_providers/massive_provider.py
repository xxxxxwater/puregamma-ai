from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from packages.data.base import AssetType, MarketQuote, ProviderSource

logger = logging.getLogger(__name__)

MASSIVE_API_BASE = os.getenv("MASSIVE_API_BASE", "https://api.polygon.io")
MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "")

EQUITY_ASSET_TYPE_MAP: dict[str, AssetType] = {
    "MSTR": "equity",
    "STRC": "preferred_equity",
    "STRD": "preferred_equity",
    "STRK": "preferred_equity",
    "STRF": "preferred_equity",
}


class MassiveProvider:
    provider_name: ProviderSource = "massive"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or MASSIVE_API_KEY
        self._session = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({"Authorization": f"Bearer {self.api_key}"})
        return self._session

    def get_quote(self, symbol: str) -> MarketQuote | None:
        if not self.enabled:
            return None
        normalized = symbol.upper()
        asset_type = EQUITY_ASSET_TYPE_MAP.get(normalized, "equity")
        try:
            client = self._client()
            resp = client.get(
                f"{MASSIVE_API_BASE}/v3/reference/tickers/{normalized}",
                timeout=10,
            )
            if resp.status_code == 404:
                logger.warning("Massive: ticker %s not found", normalized)
                return None
            resp.raise_for_status()
            ticker = resp.json()
            results = ticker.get("results", {})
            if not results:
                return None

            prev_close = None
            try:
                prev_close_resp = client.get(
                    f"{MASSIVE_API_BASE}/v2/aggs/ticker/{normalized}/prev",
                    params={"adjusted": "true"},
                    timeout=10,
                )
                prev_close_resp.raise_for_status()
                prev_data = prev_close_resp.json()
                prev_results = prev_data.get("results", [])
                if prev_results:
                    prev_close = prev_results[0].get("c")
            except Exception:
                logger.debug("Massive: prev close fetch failed for %s", normalized, exc_info=True)

            prev_day_close = results.get("prev_day", {}).get("c") or prev_close
            market_cap = results.get("market_cap") or 0
            volume_shares = results.get("volume") or 0
            price = prev_close or results.get("last_trade", {}).get("p") or 0
            volume_usd = volume_shares * price if volume_shares and price else 0

            change_24h = None
            if prev_day_close and prev_day_close > 0 and price:
                change_24h = round(((price - prev_day_close) / prev_day_close) * 100, 2)

            return MarketQuote(
                symbol=normalized,
                price=float(price),
                volume_24h=float(volume_usd),
                market_cap=float(market_cap),
                funding_rate=0.0,
                open_interest=0.0,
                volatility=0.0,
                liquidation_estimate=0.0,
                sentiment_score=0.5,
                timestamp=datetime.now(timezone.utc),
                source="massive",
                source_symbol=f"NASDAQ:{normalized}",
                change_24h=change_24h,
                is_realtime=True,
                asset_type=asset_type,
                open_interest_usd=None,
            )
        except Exception as exc:
            logger.warning("Massive: failed to fetch %s: %s", normalized, exc)
            return None

    def get_batch_quotes(self, symbols: list[str]) -> dict[str, MarketQuote]:
        result: dict[str, MarketQuote] = {}
        for symbol in symbols:
            quote = self.get_quote(symbol)
            if quote:
                result[symbol.upper()] = quote
        return result
