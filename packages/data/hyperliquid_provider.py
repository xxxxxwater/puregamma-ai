"""Hyperliquid public perp market data (no API key required).

Uses the same public `info` endpoint that feeds the console market watchlist
(`metaAndAssetCtxs`), providing mark price, perpetual funding rate, open
interest, and 24h notional volume for perp markets such as HYPE.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from packages.data.base import MarketDataProvider, MarketQuote
from packages.data.mock_provider import MockMarketDataProvider


class HyperliquidProvider(MarketDataProvider):
    provider_name = "hyperliquid"

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 4.0):
        self.base_url = (
            base_url or os.getenv("HYPERLIQUID_API_URL") or "https://api.hyperliquid.xyz"
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._mock = MockMarketDataProvider()
        self._contexts_cache: tuple[float, dict[str, dict[str, Any]]] = (0.0, {})

    def get_quote(self, symbol: str) -> MarketQuote:
        normalized = symbol.upper()
        context = self._asset_contexts().get(normalized)
        if not context:
            raise ValueError(f"{normalized} has no Hyperliquid perp market")
        return self._quote_from_context(normalized, context)

    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        contexts = self._asset_contexts()
        quotes: list[MarketQuote] = []
        for symbol in symbols:
            context = contexts.get(symbol.upper())
            if context:
                quotes.append(self._quote_from_context(symbol.upper(), context))
        return quotes

    def get_market_regime(self, quotes: list[MarketQuote]) -> str:
        return self._mock.get_market_regime(quotes)

    def _asset_contexts(self) -> dict[str, dict[str, Any]]:
        cached_at, cached = self._contexts_cache
        if cached and time.monotonic() - cached_at < 30:
            return cached
        response = httpx.post(
            f"{self.base_url}/info",
            json={"type": "metaAndAssetCtxs"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            raise ValueError("Hyperliquid returned an unexpected metaAndAssetCtxs payload")
        meta, contexts = payload[0], payload[1]
        universe = meta.get("universe", []) if isinstance(meta, dict) else []
        if not isinstance(contexts, list):
            raise ValueError("Hyperliquid returned invalid asset contexts")
        mapped: dict[str, dict[str, Any]] = {}
        for asset, context in zip(universe, contexts):
            if isinstance(asset, dict) and isinstance(context, dict) and asset.get("name"):
                mapped[str(asset["name"]).upper()] = context
        self._contexts_cache = (time.monotonic(), mapped)
        return mapped

    def _quote_from_context(self, symbol: str, context: dict[str, Any]) -> MarketQuote:
        mark_price = _float(context.get("markPx") or context.get("oraclePx"))
        open_interest = _float(context.get("openInterest"))
        return MarketQuote(
            symbol=symbol,
            price=round(mark_price, 8),
            volume_24h=round(_float(context.get("dayNtlVlm")), 2),
            market_cap=0.0,
            funding_rate=_float(context.get("funding")),
            open_interest=open_interest,
            volatility=0.0,
            liquidation_estimate=0.0,
            sentiment_score=0.0,
            timestamp=datetime.now(timezone.utc),
            source=self.provider_name,
            source_symbol=f"{symbol}-PERP",
            change_24h=None,
            is_realtime=True,
            fallback_reason=None,
            open_interest_usd=round(open_interest * mark_price, 2) if open_interest and mark_price else None,
        )


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
