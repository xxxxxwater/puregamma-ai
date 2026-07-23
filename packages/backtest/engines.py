from __future__ import annotations

from typing import Any

from packages.backtest.engine import BacktestEngine
from packages.backtest.daily_data import candle_coverage, load_candle_window, refresh_daily_candles
from packages.backtest.vectorbt_engine import run_vectorbt
from datetime import datetime, timedelta, timezone


class ExistingMockBacktestEngine:
    name = "mock"

    def run(
        self,
        strategy_name: str,
        asset: str,
        params: dict | None = None,
        *,
        db: Any = None,
    ) -> dict:
        return BacktestEngine().run(
            strategy_name, asset, params, db=db, use_real_data=False
        )


class NautilusBacktestEngine:
    name = "nautilus"

    def run(
        self,
        strategy_name: str,
        asset: str,
        params: dict | None = None,
        *,
        db: Any = None,
    ) -> dict:
        return BacktestEngine().run(
            strategy_name, asset, params, db=db, use_real_data=True
        )


class VectorBTBacktestEngine:
    name = "vectorbt"

    def run(self, strategy_name: str, asset: str, params: dict | None = None, *, db: Any = None) -> dict:
        params = params or {}
        asset = asset.upper()
        window_days = max(30, min(int(params.get("lookback_days", 365 * 3)), 365 * 3))
        if db is None:
            raise ValueError("VectorBT backtest requires the shared market data catalog")
        freshness = "binance"
        try:
            refresh_daily_candles(db, [asset])
        except Exception:
            from apps.api.config import get_settings
            if get_settings().app_environment.lower() == "production":
                raise
            # Development/test fallback keeps the contract usable without a
            # network dependency; it is explicitly labeled mock below.
            freshness = "mock"
            from datetime import datetime
            from packages.backtest.daily_data import load_candle_window
            now = datetime.now(timezone.utc)
            synthetic = [{"ts": now - timedelta(days=365 - index), "close": 100 + index * 0.15 + ((index % 11) - 5) * 0.4} for index in range(365)]
            window = {asset: synthetic}
        else:
            window = None
        end = datetime.now(timezone.utc)
        if window is None:
            window = load_candle_window(db, [asset], end - timedelta(days=window_days), end)
        spec = {"name": strategy_name, "mode": "daily", "signal": params.get("signal", "momentum"), "assets": [asset], "fast_window": int(params.get("fast_window", 12)), "slow_window": int(params.get("slow_window", 26)), "entry_threshold": float(params.get("entry_threshold", 0)), "exit_threshold": float(params.get("exit_threshold", 0)), "long_short": bool(params.get("long_short", False)), "fee_bps": float(params.get("fee_bps", 10)), "thesis": params.get("thesis", "")}
        result = run_vectorbt(spec, window)
        result["strategy_name"] = strategy_name
        result["asset"] = asset
        result["params"] = params
        result["data_snapshot"] = {"provider": freshness, "interval": "1d", "coverage": candle_coverage(db) if freshness == "binance" else {asset: {"bars": len(window[asset])}}}
        result["disclaimer"] = "Hypothetical research backtest. Past performance does not predict future results."
        return result


def get_backtest_engine(name: str):
    normalized = name.lower().strip()
    if normalized == "mock":
        return ExistingMockBacktestEngine()
    if normalized == "nautilus":
        return NautilusBacktestEngine()
    if normalized == "vectorbt":
        return VectorBTBacktestEngine()
    raise ValueError("Backtest engine must be vectorbt, mock or nautilus")
