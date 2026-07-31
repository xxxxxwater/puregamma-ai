"""Read-only private CEX account adapters (portfolio connections, P0-7).

User-provided read-only API keys are validated and read through these
adapters; secrets are only ever used in-memory for request signatures and are
stored exclusively as Fernet ciphertext on ``ExchangeConnection`` rows by the
service layer.
"""

from packages.data.cex_private.base import (
    DUST_MIN_USD_VALUE,
    USD_STABLECOINS,
    CexAdapterError,
    CexPermissionDenied,
    CexPrivateAdapter,
    NormalizedHolding,
    PermissionCheck,
    filter_dust,
)
from packages.data.cex_private.binance_private import BinancePrivateAdapter
from packages.data.cex_private.bybit_private import BybitPrivateAdapter
from packages.data.cex_private.okx_private import OkxPrivateAdapter

CEX_VENUES = ("binance", "okx", "bybit")

_ADAPTERS: dict[str, type[CexPrivateAdapter]] = {
    "binance": BinancePrivateAdapter,
    "okx": OkxPrivateAdapter,
    "bybit": BybitPrivateAdapter,
}


def adapter_for(
    venue: str,
    *,
    environment: str = "production",
    timeout_seconds: float = 10.0,
    max_response_bytes: int = 5_000_000,
) -> CexPrivateAdapter:
    cls = _ADAPTERS.get((venue or "").strip().lower())
    if cls is None:
        raise ValueError(f"Unsupported CEX venue: {venue}")
    return cls(
        environment=environment,
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
    )


__all__ = [
    "CEX_VENUES",
    "DUST_MIN_USD_VALUE",
    "USD_STABLECOINS",
    "CexAdapterError",
    "CexPermissionDenied",
    "CexPrivateAdapter",
    "NormalizedHolding",
    "PermissionCheck",
    "filter_dust",
    "adapter_for",
    "BinancePrivateAdapter",
    "OkxPrivateAdapter",
    "BybitPrivateAdapter",
]
