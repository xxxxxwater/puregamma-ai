from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from packages.backtest import daily_engine
from packages.backtest.daily_engine import DailyBar, _run_daily_asset, run_lab_backtest
from packages.backtest.strategy_spec import StrategySpec

_START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _spec(**overrides) -> StrategySpec:
    payload = {
        "name": "Review fix spec",
        "mode": "daily",
        "signal": "momentum",
        "assets": ["BTC"],
        "fast_window": 3,
        "slow_window": 5,
        "fee_bps": 10,
    }
    payload.update(overrides)
    return StrategySpec(**payload)


def _bars(closes: list[float]) -> list[DailyBar]:
    return [DailyBar(ts=_START + timedelta(days=i), close=c) for i, c in enumerate(closes)]


def _window(closes: list[float]) -> list[dict]:
    return [{"ts": _START + timedelta(days=i), "close": c} for i, c in enumerate(closes)]


def _trending(n: int = 60) -> list[float]:
    return [100.0 + i + (3.0 if i % 4 == 0 else 0.0) for i in range(n)]


def test_multi_asset_returns_are_equal_weighted_per_date():
    closes = _trending()
    single = run_lab_backtest(_spec(assets=["BTC"]), {"BTC": _window(closes)})
    multi = run_lab_backtest(
        _spec(assets=["BTC", "ETH"]), {"BTC": _window(closes), "ETH": _window(closes)}
    )
    timestamps = [point["ts"] for point in multi.equity_curve]
    assert len(timestamps) == len(set(timestamps)), "duplicate timestamps in equity curve"
    assert len(multi.daily_returns) == len(single.daily_returns)
    # Two identical assets at 1/2 weight each == one asset at full weight
    # (not 2x leverage from concatenating both return streams).
    assert multi.daily_returns == pytest.approx(single.daily_returns)
    assert multi.equity_curve[-1]["equity"] == pytest.approx(single.equity_curve[-1]["equity"])


def test_multi_asset_averages_offsetting_assets():
    up = _trending()
    flat = [100.0] * len(up)
    up_only = run_lab_backtest(_spec(assets=["BTC"]), {"BTC": _window(up)})
    mixed = run_lab_backtest(
        _spec(assets=["BTC", "ETH"]), {"BTC": _window(up), "ETH": _window(flat)}
    )
    assert mixed.daily_returns == pytest.approx([r / 2 for r in up_only.daily_returns])


def test_slippage_bps_is_charged_like_fees():
    bars = _bars(_trending())
    fee_only = _run_daily_asset(_spec(fee_bps=10, slippage_bps=0), bars)
    slip_only = _run_daily_asset(_spec(fee_bps=0, slippage_bps=10), bars)
    both = _run_daily_asset(_spec(fee_bps=10, slippage_bps=25), bars)
    assert fee_only.trades, "expected trades so costs apply"
    assert slip_only.daily_returns == pytest.approx(fee_only.daily_returns)
    assert both.equity_curve[-1]["equity"] < fee_only.equity_curve[-1]["equity"]


def test_cross_sectional_charges_slippage():
    left = [100.0 * (1.01 ** i) for i in range(60)]
    right = [100.0 * (0.995 ** i) for i in range(60)]
    window = {"BTC": _window(left), "ETH": _window(right)}
    base = dict(mode="cross_sectional", signal="relative_strength", assets=["BTC", "ETH"], long_short=True)
    without = run_lab_backtest(_spec(**base, slippage_bps=0), window)
    with_slip = run_lab_backtest(_spec(**base, slippage_bps=50), window)
    assert without.trades
    assert with_slip.equity_curve[-1]["equity"] < without.equity_curve[-1]["equity"]


def _constant_signal(monkeypatch, value: float) -> None:
    monkeypatch.setattr(daily_engine, "_daily_signal", lambda *args, **kwargs: value)


def test_long_stop_resets_peak_on_new_entry(monkeypatch):
    _constant_signal(monkeypatch, 1.0)
    spec = _spec(stop_loss_pct=0.1, rebalance_days=1, fee_bps=0)
    # Long from 100 to a 200 peak, stopped out at 150. Re-entry at 100 must
    # trail from the new entry, not the stale 200 peak (which would stop the
    # new position out immediately and repeatedly).
    closes = [100, 200, 150, 100, 100, 110, 120, 130, 125]
    result = _run_daily_asset(spec, _bars(closes))
    transitions = [(t["from"], t["to"]) for t in result.trades]
    assert transitions == [(0.0, 1.0), (1.0, 0.0), (0.0, 1.0)]


def test_short_stop_trails_running_min(monkeypatch):
    _constant_signal(monkeypatch, -1.0)
    spec = _spec(stop_loss_pct=0.05, rebalance_days=10, fee_bps=0, long_short=True)
    # Short at 100, price falls to 50, then bounces 8% to 54: a trailing stop
    # from the 50 low must fire (the stale reference of 100 never would).
    closes = [100, 50, 54, 54, 54]
    result = _run_daily_asset(spec, _bars(closes))
    transitions = [(t["from"], t["to"]) for t in result.trades]
    assert transitions == [(0.0, -1.0), (-1.0, 0.0)]
    assert result.trades[1]["ts"] == _bars(closes)[3].ts.isoformat()


def test_stop_reference_is_the_fill_not_the_signal_bar(monkeypatch):
    _constant_signal(monkeypatch, 1.0)
    spec = _spec(stop_loss_pct=0.05, rebalance_days=1, fee_bps=0)
    # Signal on the 100 close, filled at 94. The position is never down 5%
    # from its fill, so it must not be stopped out on the next bar.
    closes = [100, 94, 95, 96, 97]
    result = _run_daily_asset(spec, _bars(closes))
    assert [(t["from"], t["to"]) for t in result.trades] == [(0.0, 1.0)]


def test_cross_sectional_never_reads_the_final_close_early():
    # Flat prices except a jump on BTC's very last bar. slow (5) is a multiple
    # of rebalance_days (5): the first rebalance used to index closes[-1].
    left = [100.0] * 29 + [200.0]
    right = [100.0] * 30
    spec = _spec(mode="cross_sectional", signal="relative_strength", assets=["BTC", "ETH"],
                 long_short=True, slow_window=5, rebalance_days=5)
    result = run_lab_backtest(spec, {"BTC": _window(left), "ETH": _window(right)})
    assert result.trades == []
