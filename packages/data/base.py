from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AssetType = Literal["equity", "preferred_equity", "crypto", "credit"]
ProviderSource = Literal["nasdaq", "massive", "fmp", "alpha_vantage", "binance", "coinbase", "coingecko", "mock"]

EQUITY_SYMBOLS: set[str] = {"MSTR", "STRC", "STRD", "STRK", "STRF"}
PREFERRED_EQUITY_SYMBOLS: set[str] = {"STRC", "STRD", "STRK", "STRF"}


def asset_type_for(symbol: str) -> AssetType:
    s = symbol.upper()
    if s in PREFERRED_EQUITY_SYMBOLS:
        return "preferred_equity"
    if s in EQUITY_SYMBOLS:
        return "equity"
    return "crypto"


def is_equity(symbol: str) -> bool:
    return symbol.upper() in EQUITY_SYMBOLS


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    price: float
    volume_24h: float
    market_cap: float
    funding_rate: float
    open_interest: float
    volatility: float
    liquidation_estimate: float
    sentiment_score: float
    timestamp: datetime
    source: str = "mock"
    source_symbol: str | None = None
    change_24h: float | None = None
    is_realtime: bool = False
    fallback_reason: str | None = None
    asset_type: AssetType = "crypto"
    open_interest_usd: float | None = None


class MarketDataProvider(ABC):
    @abstractmethod
    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        raise NotImplementedError

    @abstractmethod
    def get_market_regime(self, quotes: list[MarketQuote]) -> str:
        raise NotImplementedError
