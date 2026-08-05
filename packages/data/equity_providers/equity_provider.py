from __future__ import annotations

import logging
import os
from dataclasses import replace
from packages.data.base import MarketQuote, asset_type_for
from packages.data.equity_providers.alpha_vantage_provider import AlphaVantageProvider
from packages.data.equity_providers.fmp_provider import FMPProvider
from packages.data.equity_providers.massive_provider import MassiveProvider
from packages.data.equity_providers.nasdaq_provider import NasdaqDataLinkProvider
from packages.data.mock_provider import MockMarketDataProvider

logger = logging.getLogger(__name__)

def _mock_enabled() -> bool:
    return os.environ.get("ENABLE_MOCK_MARKET_DATA", "false").lower() == "true"


def _provider_order() -> str:
    return os.environ.get("MARKET_DATA_PROVIDER", "nasdaq").lower()


EQUITY_SOURCE_LABELS: dict[str, str] = {
    "nasdaq": "Nasdaq Data Link",
    "massive": "Massive",
    "fmp": "Financial Modeling Prep",
    "alpha_vantage": "Alpha Vantage",
    "mock": "MOCK",
}

PREFERRED_SOURCE_LABELS: dict[str, str] = {
    "nasdaq": "Nasdaq Data Link",
    "massive": "Massive",
    "fmp": "Financial Modeling Prep",
    "alpha_vantage": "Alpha Vantage",
    "mock": "MOCK",
}


def equity_source_label(symbol: str, source: str) -> str:
    asset_type = asset_type_for(symbol)
    if asset_type == "preferred_equity":
        return PREFERRED_SOURCE_LABELS.get(source, source.upper())
    return EQUITY_SOURCE_LABELS.get(source, source.upper())


class EquityDataProvider:
    def __init__(self):
        self.mock = MockMarketDataProvider()
        self._providers: list = []

    def _init_providers(self) -> list:
        if self._providers:
            return self._providers
        priority = _provider_order()
        if priority == "nasdaq":
            chain = [NasdaqDataLinkProvider()]
        elif priority == "massive":
            chain = [MassiveProvider(), FMPProvider(), AlphaVantageProvider()]
        elif priority == "fmp":
            chain = [FMPProvider(), AlphaVantageProvider(), MassiveProvider()]
        elif priority == "alpha_vantage":
            chain = [AlphaVantageProvider(), FMPProvider(), MassiveProvider()]
        else:
            chain = [NasdaqDataLinkProvider()]
        self._providers = chain
        return chain

    def get_quote(self, symbol: str) -> MarketQuote:
        normalized = symbol.upper()
        providers = self._init_providers()
        errors: list[str] = []
        for provider in providers:
            if not provider.enabled:
                errors.append(f"{provider.provider_name}: no API key configured")
                continue
            try:
                quote = provider.get_quote(normalized)
                if quote:
                    return quote
                errors.append(f"{provider.provider_name}: returned no data")
            except Exception as exc:
                errors.append(f"{provider.provider_name}: {str(exc)[:160]}")

        if _mock_enabled():
            mock_quote = self.mock.get_snapshot([normalized])[0]
            asset_type = asset_type_for(normalized)
            return replace(
                mock_quote,
                source="mock",
                source_symbol=normalized,
                is_realtime=False,
                fallback_reason="; ".join(errors) if errors else "No equity data provider available",
                asset_type=asset_type,
                funding_rate=0.0,
                open_interest=0.0,
                open_interest_usd=None,
            )
        raise RuntimeError(
            f"All equity providers failed for {normalized}: "
            + ("; ".join(errors) if errors else "no providers configured")
            + ". Set ENABLE_MOCK_MARKET_DATA=true to allow mock fallback."
        )

    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        return [self.get_quote(s) for s in symbols]
