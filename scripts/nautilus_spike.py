"""Phase 0 memory measurement for the Nautilus integration decision.

Measures: (1) the RSS cost of importing nautilus_trader 1.230.0 itself, and
(2) the RSS of the current pure-Python runtime at 0/10/50 active strategies,
so the engine-replacement budget has a real baseline.
"""
from __future__ import annotations

import os
import resource


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def measure_import_cost() -> None:
    base = rss_mb()
    import nautilus_trader  # noqa: F401
    from nautilus_trader.live.node import TradingNode  # noqa: F401
    from nautilus_trader.backtest.node import BacktestNode  # noqa: F401

    print(f"nautilus_trader={getattr(nautilus_trader, '__version__', '?')} "
          f"import_rss_mb={rss_mb() - base:.1f} (delta) total_rss_mb={rss_mb():.1f}")


def measure_runtime_strategies(count: int) -> None:
    import tempfile

    from app.runtime_manager import RuntimeManager

    manager = RuntimeManager(os.path.join(tempfile.mkdtemp(), "runtime.sqlite3"))
    for i in range(count):
        manager.command(
            "activate",
            f"spike-{i}",
            {
                "run_id": f"run-{i}",
                "strategy_id": f"strategy-{i}",
                "strategy_version": 1,
                "account_id": "paper-1",
                "mode": "PAPER",
                "strategy": {
                    "name": "spike",
                    "instruments": ["BTCUSDT"],
                    "entry_rules": [{"threshold": 0.001}],
                    "risk": {"max_position": 1, "max_notional": 10000},
                },
            },
        )
    manager.refresh_market_data(["BTCUSDT"], force=True)
    print(f"runtime_strategies={count} steady_rss_mb={rss_mb():.1f}")


if __name__ == "__main__":
    measure_import_cost()
    for count in (0, 10, 50):
        measure_runtime_strategies(count)
