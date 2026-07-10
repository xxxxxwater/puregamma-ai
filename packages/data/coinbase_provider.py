from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import httpx

from packages.data.base import MarketDataProvider, MarketQuote
from packages.data.mock_provider import MockMarketDataProvider


COINBASE_PRODUCTS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "HYPE": "HYPE-USD",
}


class CoinbaseProvider(MarketDataProvider):
    provider_name = "coinbase"

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 4.0):
        self.base_url = (base_url or os.getenv("COINBASE_REST_BASE_URL") or "https://api.exchange.coinbase.com").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._mock = MockMarketDataProvider()

    def get_quote(self, symbol: str) -> MarketQuote:
        normalized = symbol.upper()
        product_id = COINBASE_PRODUCTS.get(normalized)
        if not product_id:
            raise ValueError(f"{normalized} has no Coinbase USD product mapping")

        ticker_response = httpx.get(f"{self.base_url}/products/{product_id}/ticker", timeout=self.timeout_seconds)
        ticker_response.raise_for_status()
        ticker = ticker_response.json()

        stats: dict[str, Any] = {}
        try:
            stats_response = httpx.get(f"{self.base_url}/products/{product_id}/stats", timeout=self.timeout_seconds)
            stats_response.raise_for_status()
            stats = stats_response.json()
        except Exception:
            stats = {}

        return self._quote_from_payload(normalized, product_id, ticker, stats)

    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        quotes: list[MarketQuote] = []
        for symbol in symbols:
            try:
                quotes.append(self.get_quote(symbol))
            except Exception:
                continue
        return quotes

    def get_market_regime(self, quotes: list[MarketQuote]) -> str:
        return self._mock.get_market_regime(quotes)

    def _quote_from_payload(
        self,
        symbol: str,
        source_symbol: str,
        ticker: dict[str, Any],
        stats: dict[str, Any],
    ) -> MarketQuote:
        fallback = self._mock.get_snapshot([symbol])[0]
        price = _float(ticker.get("price") or stats.get("last"), fallback.price)
        base_volume = _float(stats.get("volume") or ticker.get("volume"), fallback.volume_24h / max(price, 1.0))
        open_price = _float(stats.get("open"), 0.0)
        change_24h = ((price - open_price) / open_price * 100) if open_price > 0 else None

        return replace(
            fallback,
            price=round(price, 8),
            volume_24h=round(base_volume * price, 2),
            timestamp=_parse_coinbase_time(ticker.get("time")),
            source=self.provider_name,
            source_symbol=source_symbol,
            change_24h=round(change_24h, 4) if change_24h is not None else None,
            is_realtime=True,
            fallback_reason=None,
        )


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_coinbase_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        return datetime.now(timezone.utc)
    text = value.replace("Z", "+00:00")
    if "." in text:
        head, tail = text.split(".", 1)
        fraction, offset = tail[:6], ""
        if "+" in tail:
            fraction, offset = tail.split("+", 1)
            offset = "+" + offset
        elif "-" in tail:
            fraction, offset = tail.split("-", 1)
            offset = "-" + offset
        text = f"{head}.{fraction[:6].ljust(6, '0')}{offset}"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
