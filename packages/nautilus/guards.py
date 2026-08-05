from __future__ import annotations

import os


LIVE_TRADING_ENABLED = False
ALLOW_LIVE_ORDER_ENV = "NAUTILUS_ALLOW_LIVE_ORDER"
LIVE_TRADING_ENV = "NAUTILUS_LIVE_TRADING_ENABLED"


class LiveTradingDisabledError(RuntimeError):
    pass


def live_trading_status() -> dict[str, bool | str]:
    env_enabled = os.getenv(LIVE_TRADING_ENV, "false").lower() == "true"
    env_order_allowed = os.getenv(ALLOW_LIVE_ORDER_ENV, "false").lower() == "true"
    return {
        "enabled": False,
        "compiled_guard_enabled": LIVE_TRADING_ENABLED,
        LIVE_TRADING_ENV: env_enabled,
        ALLOW_LIVE_ORDER_ENV: env_order_allowed,
    }


def assert_live_trading_disabled() -> None:
    status = live_trading_status()
    if status["enabled"] is not False or LIVE_TRADING_ENABLED is not False:
        raise LiveTradingDisabledError("Live trading must remain disabled in PureGamma research mode.")
