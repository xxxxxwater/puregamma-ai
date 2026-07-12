from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSettings:
    runtime_secret: str = os.getenv("NAUTILUS_RUNTIME_SECRET", "dev-runtime-secret")
    state_db: str = os.getenv("NAUTILUS_RUNTIME_STATE_DB", "./nautilus_runtime.sqlite3")
    execution_mode: str = os.getenv("NAUTILUS_EXECUTION_MODE", "paper").upper()
    live_trading_enabled: bool = (
        os.getenv("NAUTILUS_LIVE_TRADING_ENABLED", "false").lower() == "true"
    )
    allow_live_order: bool = (
        os.getenv("NAUTILUS_ALLOW_LIVE_ORDER", "false").lower() == "true"
    )
    allow_withdrawal: bool = (
        os.getenv("NAUTILUS_ALLOW_WITHDRAWAL", "false").lower() == "true"
    )
    allow_transfer: bool = (
        os.getenv("NAUTILUS_ALLOW_TRANSFER", "false").lower() == "true"
    )
    max_message_bytes: int = int(
        os.getenv("NAUTILUS_RUNTIME_MAX_MESSAGE_BYTES", "262144")
    )
    public_market_data_enabled: bool = (
        os.getenv("NAUTILUS_PUBLIC_MARKET_DATA_ENABLED", "true").lower() == "true"
    )
    hyperliquid_public_url: str = os.getenv(
        "NAUTILUS_HYPERLIQUID_PUBLIC_URL", "https://api.hyperliquid.xyz"
    )
    coinbase_public_url: str = os.getenv(
        "NAUTILUS_COINBASE_PUBLIC_URL", "https://api.exchange.coinbase.com"
    )
    market_data_timeout_seconds: float = float(
        os.getenv("NAUTILUS_MARKET_DATA_TIMEOUT_SECONDS", "5")
    )
    market_data_cache_ttl_seconds: int = int(
        os.getenv("NAUTILUS_MARKET_DATA_CACHE_TTL_SECONDS", "5")
    )
    market_data_failure_threshold: int = int(
        os.getenv("NAUTILUS_MARKET_DATA_FAILURE_THRESHOLD", "3")
    )
    market_data_recovery_seconds: int = int(
        os.getenv("NAUTILUS_MARKET_DATA_RECOVERY_SECONDS", "60")
    )


def get_settings() -> RuntimeSettings:
    return RuntimeSettings()
