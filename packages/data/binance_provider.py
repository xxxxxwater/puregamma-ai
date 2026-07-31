from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from packages.data.base import MarketDataProvider, MarketQuote
from packages.data.mock_provider import MockMarketDataProvider
from packages.data.provider import (
    DataProvenance,
    DataSourceHealth,
    DataSourceProvider,
    DataSourceStatus,
    DataSourceSyncResult,
    ProviderError,
)


BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    # HYPE has no Binance USDT spot pair; it is served by Coinbase/Hyperliquid.
}


class BinanceProvider(MarketDataProvider, DataSourceProvider):
    id = "binance"
    name = "Binance Public Market Data"
    category = "market"
    provider_name = "binance"

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 4.0):
        self.base_url = (
            base_url or os.getenv("BINANCE_REST_BASE_URL") or "https://api.binance.com"
        ).rstrip("/")
        self.futures_base_url = (
            os.getenv("BINANCE_FUTURES_BASE_URL") or "https://fapi.binance.com"
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._mock = MockMarketDataProvider()

    def get_quote(self, symbol: str) -> MarketQuote:
        normalized = symbol.upper()
        binance_symbol = BINANCE_SYMBOLS.get(normalized)
        if not binance_symbol:
            raise ValueError(f"{normalized} has no Binance USDT spot mapping")

        response = httpx.get(
            f"{self.base_url}/api/v3/ticker/24hr",
            params={"symbol": binance_symbol},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        quote = self._quote_from_payload(normalized, binance_symbol, payload)
        return self._with_futures_metrics(quote, binance_symbol)

    def _with_futures_metrics(self, quote: MarketQuote, source_symbol: str) -> MarketQuote:
        """Attach perpetual funding rate and open interest from public futures endpoints.

        These endpoints need no API key. Any failure leaves the spot quote
        unchanged (funding/OI stay 0) so spot data is never blocked by a
        futures outage.
        """
        try:
            premium = httpx.get(
                f"{self.futures_base_url}/fapi/v1/premiumIndex",
                params={"symbol": source_symbol},
                timeout=self.timeout_seconds,
            )
            premium.raise_for_status()
            premium_payload = premium.json()
            funding_rate = _float(premium_payload.get("lastFundingRate"))
            mark_price = _float(premium_payload.get("markPrice")) or quote.price
            open_interest = 0.0
            open_interest_usd: float | None = None
            oi = httpx.get(
                f"{self.futures_base_url}/fapi/v1/openInterest",
                params={"symbol": source_symbol},
                timeout=self.timeout_seconds,
            )
            oi.raise_for_status()
            oi_payload = oi.json()
            open_interest = _float(oi_payload.get("openInterest"))
            if open_interest and mark_price:
                open_interest_usd = round(open_interest * mark_price, 2)
            if not (funding_rate or open_interest):
                return quote
            return replace(
                quote,
                funding_rate=funding_rate,
                open_interest=open_interest,
                open_interest_usd=open_interest_usd,
            )
        except Exception:
            return quote

    def _get_json(self, path: str, params: dict | None = None) -> Any:
        try:
            response = httpx.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=self.timeout_seconds,
                headers={"User-Agent": "PureGamma AI/1.0 public-market"},
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", "Binance request timed out") from exc
        if response.status_code == 429:
            raise ProviderError(
                "rate_limited", "Binance rate limit reached", status_code=429
            )
        if response.status_code >= 400:
            raise ProviderError(
                "http_error",
                f"Binance returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        return response.json()

    def ping(self) -> bool:
        return self._get_json("/api/v3/ping") == {}

    def server_time(self) -> datetime:
        payload = self._get_json("/api/v3/time")
        return datetime.fromtimestamp(
            int(payload["serverTime"]) / 1000, tz=timezone.utc
        )

    def exchange_info(self, symbols: list[str] | None = None) -> dict:
        mapped = [
            BINANCE_SYMBOLS.get(symbol.upper(), symbol.upper())
            for symbol in (symbols or [])
        ]
        params = {"symbols": __import__("json").dumps(mapped)} if mapped else None
        return self._get_json("/api/v3/exchangeInfo", params)

    def current_price(self, symbol: str) -> Decimal:
        source_symbol = BINANCE_SYMBOLS.get(symbol.upper(), symbol.upper())
        return _decimal(
            self._get_json("/api/v3/ticker/price", {"symbol": source_symbol})["price"]
        )

    def klines(
        self, symbol: str, interval: str = "1h", limit: int = 100
    ) -> list[list[Any]]:
        if interval not in {"1m", "5m", "15m", "1h", "4h", "1d"}:
            raise ValueError("Unsupported Binance kline interval")
        return self._get_json(
            "/api/v3/klines",
            {
                "symbol": BINANCE_SYMBOLS.get(symbol.upper(), symbol.upper()),
                "interval": interval,
                "limit": min(max(limit, 1), 500),
            },
        )

    def depth(self, symbol: str, limit: int = 20) -> dict:
        allowed = min(
            (value for value in (5, 10, 20, 50, 100) if value >= limit), default=100
        )
        return self._get_json(
            "/api/v3/depth",
            {
                "symbol": BINANCE_SYMBOLS.get(symbol.upper(), symbol.upper()),
                "limit": allowed,
            },
        )

    def health_check(self) -> DataSourceHealth:
        started = datetime.now(timezone.utc)
        try:
            self.ping()
            latency = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            return DataSourceHealth(
                DataSourceStatus.HEALTHY,
                "Binance public REST reachable",
                latency_ms=latency,
            )
        except ProviderError as exc:
            status = (
                DataSourceStatus.RATE_LIMITED
                if exc.code == "rate_limited"
                else DataSourceStatus.ERROR
            )
            return DataSourceHealth(status, str(exc))

    def sync(self, symbols: list[str] | None = None) -> DataSourceSyncResult:
        records: list[dict] = []
        errors: list[str] = []
        for asset in symbols or list(BINANCE_SYMBOLS):
            source_symbol = BINANCE_SYMBOLS.get(asset.upper())
            if not source_symbol:
                errors.append(f"{asset}: no Binance spot mapping")
                continue
            try:
                payload = self._get_json(
                    "/api/v3/ticker/24hr", {"symbol": source_symbol}
                )
                fetched_at = datetime.now(timezone.utc)
                source_time = (
                    datetime.fromtimestamp(
                        int(payload.get("closeTime", 0)) / 1000, tz=timezone.utc
                    )
                    if payload.get("closeTime")
                    else fetched_at
                )
                records.append(
                    {
                        "symbol": source_symbol,
                        "base_asset": asset.upper(),
                        "quote_asset": "USDT",
                        "asset_type": "spot",
                        "provider": "binance",
                        "price": _decimal_or_none(payload.get("lastPrice")),
                        "change_24h_pct": _decimal_or_none(
                            payload.get("priceChangePercent")
                        ),
                        "volume_24h_base": _decimal_or_none(payload.get("volume")),
                        "volume_24h_quote": _decimal_or_none(
                            payload.get("quoteVolume")
                        ),
                        "high_24h": _decimal_or_none(payload.get("highPrice")),
                        "low_24h": _decimal_or_none(payload.get("lowPrice")),
                        "bid": _decimal_or_none(payload.get("bidPrice")),
                        "ask": _decimal_or_none(payload.get("askPrice")),
                        "source_timestamp": source_time,
                        "fetched_at": fetched_at,
                        "provenance_json": DataProvenance(
                            provider="binance",
                            source_url=f"{self.base_url}/api/v3/ticker/24hr",
                            source_timestamp=source_time,
                            fetched_at=fetched_at,
                        ).as_dict(),
                    }
                )
            except Exception as exc:
                errors.append(f"{asset}: {str(exc)[:200]}")
        status = (
            DataSourceStatus.ERROR
            if not records
            else DataSourceStatus.PARTIAL
            if errors
            else DataSourceStatus.HEALTHY
        )
        return DataSourceSyncResult(
            status=status, records=records, fetched_count=len(records), errors=errors
        )

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
        self, symbol: str, source_symbol: str, payload: dict[str, Any]
    ) -> MarketQuote:
        close_time_ms = _float(payload.get("closeTime"), default=0.0)
        timestamp = (
            datetime.fromtimestamp(close_time_ms / 1000, tz=timezone.utc)
            if close_time_ms > 0
            else datetime.now(timezone.utc)
        )
        return MarketQuote(
            symbol=symbol,
            price=round(_float(payload.get("lastPrice")), 8),
            volume_24h=round(_float(payload.get("quoteVolume")), 2),
            market_cap=0.0,
            funding_rate=0.0,
            open_interest=0.0,
            volatility=0.0,
            liquidation_estimate=0.0,
            sentiment_score=0.0,
            timestamp=timestamp,
            source=self.provider_name,
            source_symbol=source_symbol,
            change_24h=round(_float(payload.get("priceChangePercent"), 0.0), 4),
            is_realtime=True,
            fallback_reason=None,
        )


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProviderError(
            "invalid_number", "Binance returned an invalid decimal"
        ) from exc


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return _decimal(value)
