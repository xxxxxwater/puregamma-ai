from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from packages.backtest.engine import BacktestEngine
from packages.backtest.vectorbt_engine import run_vectorbt


def test_mock_backtest_cannot_be_labeled_live():
    result = BacktestEngine().run("BTC momentum breakout", "BTC", {"lookback_days": 10})
    assert result["mode"] == "mock"
    assert result["is_live"] is False
    assert result["execution_environment"] == "research_mock"
    assert result["live_trading"]["enabled"] is False


def test_backtesting_standard_documents_bar_close_and_costs():
    text = Path("docs/quant/BACKTESTING_STANDARD.md").read_text()
    assert "bar close" in text
    assert "Fees must be included" in text
    assert "Slippage must be included" in text


def test_vectorbt_result_includes_all_plotly_research_figures():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    window = {
        "BTC": [
            {"ts": start + timedelta(days=index), "close": 100 + index}
            for index in range(40)
        ]
    }
    result = run_vectorbt(
        {
            "name": "BTC trend",
            "assets": ["BTC"],
            "signal": "momentum",
            "fast_window": 4,
            "slow_window": 10,
            "fee_bps": 10,
        },
        window,
    )

    assert {"equity", "drawdown", "benchmark_comparison", "trades", "positions"} <= set(result["charts"])
    assert result["benchmark_curve"]
    assert all("data" in figure and "layout" in figure for figure in result["charts"].values())
