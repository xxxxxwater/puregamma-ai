from __future__ import annotations

import os
from dataclasses import replace
from typing import Protocol

from packages.data.base import MarketDataProvider, MarketQuote, asset_type_for, is_equity
from packages.data.binance_provider import BinanceProvider
from packages.data.coinbase_provider import CoinbaseProvider
from packages.data.equity_providers.equity_provider import EquityDataProvider, equity_source_label
from packages.data.mock_provider import MockMarketDataProvider


class QuoteProvider(Protocol):
    provider_name: str

    def get_quote(self, symbol: str) -> MarketQuote:
        ...


class PublicMarketDataProvider(MarketDataProvider):
    """Composite market data provider for dashboard REST quotes.

    Crypto assets (BTC, ETH, SOL, HYPE) route through Binance → Coinbase → mock.
    Equity assets (MSTR, STRC, STRD, STRK, STRF) route through Massive → FMP → Alpha Vantage → mock (dev only).
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
        self.providers = providers if providers is not None else self._providers_for_mode(self.mode)
        self._equity_provider: EquityDataProvider | None = None

    @property
    def equity_provider(self) -> EquityDataProvider:
        if self._equity_provider is None:
            self._equity_provider = EquityDataProvider()
        return self._equity_provider

    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        crypto_symbols = [s for s in symbols if not is_equity(s)]
        equity_symbols = [s for s in symbols if is_equity(s)]

        mock_all = self.fallback_provider.get_snapshot(symbols)
        mock_map = {q.symbol: q for q in mock_all}

        if self.mode == "mock":
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
                fallback = mock_map.get(normalized) or self.fallback_provider.get_snapshot([normalized])[0]
                resolved[normalized] = replace(
                    fallback,
                    source="mock",
                    source_symbol=normalized,
                    is_realtime=False,
                    fallback_reason="; ".join(errors) if errors else "No Binance/Coinbase public USD market mapping",
                )
                self.last_errors[normalized] = errors

        for symbol in equity_symbols:
            normalized = symbol.upper()
            try:
                quote = self.equity_provider.get_quote(normalized)
                resolved[normalized] = quote
            except RuntimeError:
                mock_quote = mock_map.get(normalized) or self.fallback_provider.get_snapshot([normalized])[0]
                asset_type = asset_type_for(normalized)
                resolved[normalized] = replace(
                    mock_quote,
                    source="mock",
                    source_symbol=normalized,
                    is_realtime=False,
                    fallback_reason="All equity providers failed and mock disabled",
                    asset_type=asset_type,
                    funding_rate=0.0,
                    open_interest=0.0,
                    open_interest_usd=None,
                )

        for symbol in symbols:
            quotes.append(resolved[symbol.upper()])

        return quotes

    def get_market_regime(self, quotes: list[MarketQuote]) -> str:
        return self.fallback_provider.get_market_regime(quotes)

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
        return [BinanceProvider(), CoinbaseProvider()]
