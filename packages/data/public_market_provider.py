from __future__ import annotations

import os
from dataclasses import replace
from typing import Protocol

from packages.data.base import (
    MarketDataProvider,
    MarketQuote,
    is_equity,
)
from packages.data.binance_provider import BinanceProvider
from packages.data.coinbase_provider import CoinbaseProvider
from packages.data.equity_providers.equity_provider import EquityDataProvider
from packages.data.hyperliquid_provider import HyperliquidProvider
from packages.data.mock_provider import MockMarketDataProvider


class QuoteProvider(Protocol):
    provider_name: str

    def get_quote(self, symbol: str) -> MarketQuote: ...


class PublicMarketDataProvider(MarketDataProvider):
    """Composite market data provider for dashboard REST quotes.

    Production never substitutes mock quotes when a live provider is unavailable.
    """

    def __init__(
        self,
        providers: list[QuoteProvider] | None = None,
        fallback_provider: MockMarketDataProvider | None = None,
        mode: str | None = None,
    ):
        self.mode = (mode or os.getenv("MARKET_DATA_MODE") or "auto").lower()
        self.fallback_provider = fallback_provider or MockMarketDataProvider()
        self.last_errors: dict[str, list[str]] = {}
        self.providers = (
            providers if providers is not None else self._providers_for_mode(self.mode)
        )
        self._equity_provider: EquityDataProvider | None = None

    @property
    def equity_provider(self) -> EquityDataProvider:
        if self._equity_provider is None:
            self._equity_provider = EquityDataProvider()
        return self._equity_provider

    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        crypto_symbols = [s for s in symbols if not is_equity(s)]
        equity_symbols = [s for s in symbols if is_equity(s)]

        if self.mode == "mock":
            mock_map = {
                q.symbol: q for q in self.fallback_provider.get_snapshot(symbols)
            }
            return [
                replace(mock_map[s], fallback_reason="MARKET_DATA_MODE=mock")
                for s in symbols
            ]

        quotes: list[MarketQuote] = []
        resolved: dict[str, MarketQuote] = {}

        for symbol in crypto_symbols:
            normalized = symbol.upper()
            errors: list[str] = []
            quote = self._first_live_quote(normalized, errors)
            if quote:
                resolved[normalized] = quote
            else:
                self.last_errors[normalized] = errors

        for symbol in equity_symbols:
            normalized = symbol.upper()
            try:
                quote = self.equity_provider.get_quote(normalized)
                resolved[normalized] = quote
            except RuntimeError as exc:
                self.last_errors[normalized] = [str(exc)[:200]]

        for symbol in symbols:
            quote = resolved.get(symbol.upper())
            if quote:
                quotes.append(quote)

        return self._enrich_with_hyperliquid(quotes)

    def _enrich_with_hyperliquid(self, quotes: list[MarketQuote]) -> list[MarketQuote]:
        """Attach perp funding/OI from the Hyperliquid public feed.

        Crypto quotes that carry no derivatives metrics from the primary chain
        (e.g. HYPE served from Coinbase spot) are enriched with the same public
        Hyperliquid data that feeds the console watchlist. Any failure leaves
        the original quotes untouched.
        """
        missing = [
            quote.symbol
            for quote in quotes
            if quote.asset_type == "crypto" and not quote.funding_rate and not quote.open_interest
        ]
        if not missing:
            return quotes
        try:
            perp = {quote.symbol: quote for quote in HyperliquidProvider().get_snapshot(missing)}
        except Exception:
            return quotes
        enriched: list[MarketQuote] = []
        for quote in quotes:
            metrics = perp.get(quote.symbol)
            if metrics and (metrics.funding_rate or metrics.open_interest):
                enriched.append(
                    replace(
                        quote,
                        funding_rate=metrics.funding_rate,
                        open_interest=metrics.open_interest,
                        open_interest_usd=metrics.open_interest_usd,
                    )
                )
            else:
                enriched.append(quote)
        return enriched

    def get_market_regime(self, quotes: list[MarketQuote]) -> str:
        if not quotes:
            return "unavailable"
        changes = [quote.change_24h for quote in quotes if quote.change_24h is not None]
        average = sum(changes) / len(changes) if changes else 0.0
        return "risk_on" if average > 1 else "risk_off" if average < -1 else "neutral"

    def _first_live_quote(self, symbol: str, errors: list[str]) -> MarketQuote | None:
        for provider in self.providers:
            try:
                return provider.get_quote(symbol)
            except Exception as exc:
                errors.append(f"{provider.provider_name}: {str(exc)[:160]}")
        return None

    @staticmethod
    def _providers_for_mode(mode: str) -> list[QuoteProvider]:
        if mode == "binance":
            return [BinanceProvider()]
        if mode == "coinbase":
            return [CoinbaseProvider()]
        if mode == "mock":
            return []
        # Hyperliquid is the final live fallback for the headline crypto set.
        # This is essential for HYPE, which may not have a spot listing on a
        # centralized venue at all times but trades natively as a Hyperliquid
        # perpetual.
        return [BinanceProvider(), CoinbaseProvider(), HyperliquidProvider()]
