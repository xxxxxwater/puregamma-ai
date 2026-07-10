from __future__ import annotations

from pathlib import Path

from packages.backtest.engine import BacktestEngine


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
