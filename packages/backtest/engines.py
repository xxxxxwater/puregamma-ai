from __future__ import annotations

from typing import Any

from packages.backtest.engine import BacktestEngine


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


def get_backtest_engine(name: str):
    normalized = name.lower().strip()
    if normalized == "mock":
        return ExistingMockBacktestEngine()
    if normalized == "nautilus":
        return NautilusBacktestEngine()
    raise ValueError("Backtest engine must be mock or nautilus")
