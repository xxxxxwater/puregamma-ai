from __future__ import annotations

from copy import deepcopy

from packages.nautilus.guards import assert_live_trading_disabled, live_trading_status


STANDARD_METRIC_KEYS = {
    "total_return",
    "sharpe",
    "max_drawdown",
    "win_rate",
    "trade_count",
    "turnover",
    "exposure_time",
    "tail_loss_95",
}


def standardize_backtest_result(result: dict) -> dict:
    assert_live_trading_disabled()
    standardized = deepcopy(result)
    metrics = standardized.setdefault("metrics", {})
    for key in STANDARD_METRIC_KEYS:
        metrics.setdefault(key, 0.0)

    mode = standardized.get("mode", "mock")
    is_live = bool(standardized.get("is_live", False))
    if mode == "mock" or standardized.get("engine") == "puregamma_mock_backtest":
        is_live = False
        standardized["mode"] = "mock"
        standardized["execution_environment"] = "research_mock"

    standardized["is_live"] = is_live
    standardized["paper_trading"] = bool(standardized.get("paper_trading", False)) and not is_live
    standardized["live_trading"] = live_trading_status()
    standardized["disclaimer"] = standardized.get(
        "disclaimer",
        "Research backtest only. Past results do not guarantee future results.",
    )
    return standardized
