from __future__ import annotations

from packages.nautilus.guards import assert_live_trading_disabled, live_trading_status
from packages.nautilus.result_parser import STANDARD_METRIC_KEYS, standardize_backtest_result


def test_standardized_nautilus_metrics_include_required_fields():
    result = standardize_backtest_result(
        {
            "mode": "mock",
            "engine": "puregamma_mock_backtest",
            "is_live": True,
            "metrics": {"total_return": 0.1},
        }
    )
    assert result["is_live"] is False
    assert result["mode"] == "mock"
    assert STANDARD_METRIC_KEYS.issubset(result["metrics"].keys())


def test_live_trading_disabled_guard_remains_active(monkeypatch):
    monkeypatch.setenv("NAUTILUS_LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("NAUTILUS_ALLOW_LIVE_ORDER", "true")
    assert_live_trading_disabled()
    status = live_trading_status()
    assert status["enabled"] is False
    assert status["compiled_guard_enabled"] is False
