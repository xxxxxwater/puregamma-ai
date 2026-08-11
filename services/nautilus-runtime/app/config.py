from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSettings:
    app_environment: str = os.getenv("APP_ENV", "development")
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
    binance_testnet_base_url: str = os.getenv(
        "NAUTILUS_BINANCE_TESTNET_BASE_URL", "https://testnet.binance.vision"
    )
    binance_testnet_recv_window_ms: int = int(
        os.getenv("NAUTILUS_BINANCE_TESTNET_RECV_WINDOW_MS", "5000")
    )
    binance_testnet_timeout_seconds: float = float(
        os.getenv("NAUTILUS_BINANCE_TESTNET_TIMEOUT_SECONDS", "10")
    )
    # Testnet order submission stays OFF unless explicitly enabled. PAPER runs
    # never submit anywhere; this gate only matters for SHADOW runs whose venue
    # resolves to the Binance testnet adapter.
    testnet_submit_enabled: bool = (
        os.getenv("NAUTILUS_TESTNET_SUBMIT_ENABLED", "false").lower() == "true"
    )
    # Execution backend: legacy is the current pure-Python runtime. When the
    # NautilusTrader engine lands (Phase 1), 'nautilus' selects it and
    # 'legacy' remains the rollback path.
    engine_backend: str = os.getenv("NAUTILUS_ENGINE_BACKEND", "legacy").lower()


def get_settings() -> RuntimeSettings:
    settings = RuntimeSettings()
    if settings.app_environment.lower() == "production":
        errors: list[str] = []
        if settings.runtime_secret == "dev-runtime-secret" or len(settings.runtime_secret) < 24:
            errors.append("NAUTILUS_RUNTIME_SECRET must be a strong non-default value")
        if settings.execution_mode.lower() not in {"paper", "shadow"}:
            errors.append("NAUTILUS_EXECUTION_MODE must remain paper or shadow")
        if settings.live_trading_enabled or settings.allow_live_order:
            errors.append("Live order execution must remain disabled")
        if settings.allow_withdrawal or settings.allow_transfer:
            errors.append("Withdrawal and transfer capabilities are forbidden")
        if errors:
            raise RuntimeError("; ".join(errors))
    return settings
