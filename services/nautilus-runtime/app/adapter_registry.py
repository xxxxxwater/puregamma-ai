from __future__ import annotations

from adapters.binance_spot_testnet import BinanceSpotTestnetAdapter
from adapters.coinbase_advanced import CoinbaseAdvancedAdapter
from adapters.hyperliquid import HyperliquidAdapter
from adapters.unavailable import UnavailableAdapter
from app.exchange_gateway import MockExchangeGateway

# Environments that would imply real funds. Live execution is compiled out of
# this release, so any account pointing at one resolves to a fail-closed
# UnavailableAdapter instead of ever silently mocking or submitting.
DISABLED_ENVIRONMENTS = {"live", "prod", "production", "mainnet"}


def adapter_key(account: dict | None) -> tuple[str, str]:
    account = account or {}
    venue = str(account.get("venue") or "MOCK").upper()
    environment = str(account.get("environment") or "paper").lower()
    return venue, environment


def adapter_for(account: dict | None, config=None, store=None):
    """Resolve the exchange gateway for an account record.

    Selection is by (venue, environment) taken from the account record carried
    in the run config. venue=MOCK keeps the existing simulated gateway with no
    behavior change. Unknown venues fail closed with an explicit reason.
    """
    venue, environment = adapter_key(account)
    if venue == "MOCK":
        return MockExchangeGateway(store)
    if environment in DISABLED_ENVIRONMENTS:
        return UnavailableAdapter(
            f"{venue} {environment} execution is disabled in this release",
            venue=venue,
            environment=environment,
        )
    if venue == "BINANCE" and environment == "testnet":
        if not getattr(config, "testnet_submit_enabled", False):
            # Default is OFF; config=None also fails closed.
            return UnavailableAdapter(
                "Binance testnet submission is disabled (NAUTILUS_TESTNET_SUBMIT_ENABLED must be true)",
                venue=venue,
                environment=environment,
            )
        kwargs = {}
        if config is not None:
            kwargs = {
                "base_url": config.binance_testnet_base_url,
                "recv_window_ms": config.binance_testnet_recv_window_ms,
                "timeout": config.binance_testnet_timeout_seconds,
            }
        return BinanceSpotTestnetAdapter(**kwargs)
    if venue == "HYPERLIQUID":
        return HyperliquidAdapter()
    if venue in {"COINBASE", "COINBASE_ADVANCED"}:
        return CoinbaseAdvancedAdapter()
    return UnavailableAdapter(
        f"no adapter registered for venue={venue} environment={environment}",
        venue=venue,
        environment=environment,
    )
