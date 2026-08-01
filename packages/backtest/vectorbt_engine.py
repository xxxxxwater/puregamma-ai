"""Small VectorBT-compatible research engine.

VectorBT is used when installed in production. The pure-Python path keeps local
and test environments functional while preserving the same result contract.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from packages.backtest.metrics import calculate_metrics
from packages.backtest.quantstats_adapter import enrich_metrics

PROGRESS_INTERVAL_BARS = 50


def _log_summary_metrics(logger: Any | None, metrics: dict[str, Any]) -> None:
    """Emit the compact set of figures useful in a terminal transcript."""
    if not logger:
        return
    for name in ("sharpe", "max_drawdown", "win_rate"):
        value = metrics.get(name)
        if isinstance(value, (int, float)):
            logger.metric(name, float(value))


def _signal(closes: list[float], index: int, fast: int, slow: int, signal: str, threshold: float, long_short: bool) -> float:
    if index < slow:
        return 0.0
    history = closes[:index]
    fast_avg = sum(history[-fast:]) / fast
    slow_avg = sum(history[-slow:]) / slow
    spread = (fast_avg - slow_avg) / slow_avg if slow_avg else 0.0
    if signal == "mean_reversion":
        deviation = (history[-1] - slow_avg) / slow_avg if slow_avg else 0.0
        if deviation < -threshold:
            return 1.0
        if long_short and deviation > threshold:
            return -1.0
        return 0.0
    if signal == "breakout":
        high = max(history[-slow:])
        low = min(history[-slow:])
        if history[-1] >= high * (1 + threshold):
            return 1.0
        if long_short and history[-1] <= low * (1 - threshold):
            return -1.0
        return 0.0
    if spread > threshold:
        return 1.0
    if long_short and spread < -threshold:
        return -1.0
    return 0.0


def _drawdown_curve(equity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    peak = 0.0
    drawdown = []
    for item in equity:
        peak = max(peak, float(item["equity"]))
        drawdown.append({"ts": item["ts"], "drawdown": round(float(item["equity"]) / peak - 1, 8) if peak else 0.0})
    return drawdown


def _charts(
    equity: list[dict[str, Any]],
    drawdown: list[dict[str, Any]],
    benchmark: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    strategy_x = [item["ts"] for item in equity]
    strategy_y = [item["equity"] for item in equity]
    benchmark_x = [item["ts"] for item in benchmark]
    benchmark_y = [item["equity"] for item in benchmark]
    position_data = []
    for asset in sorted({str(item["asset"]) for item in positions}):
        points = [item for item in positions if item["asset"] == asset]
        position_data.append({"x": [item["ts"] for item in points], "y": [item["weight"] for item in points], "type": "scatter", "mode": "lines", "name": asset})
    return {
        "equity": {"data": [{"x": strategy_x, "y": strategy_y, "type": "scatter", "mode": "lines", "name": "Strategy"}], "layout": {"title": "Equity Curve", "template": "plotly_dark"}},
        "drawdown": {"data": [{"x": [item["ts"] for item in drawdown], "y": [item["drawdown"] for item in drawdown], "type": "scatter", "mode": "lines", "fill": "tozeroy", "name": "Drawdown"}], "layout": {"title": "Drawdown", "template": "plotly_dark"}},
        "benchmark_comparison": {"data": [{"x": strategy_x, "y": strategy_y, "type": "scatter", "mode": "lines", "name": "Strategy"}, {"x": benchmark_x, "y": benchmark_y, "type": "scatter", "mode": "lines", "name": "Equal-weight benchmark"}], "layout": {"title": "Strategy vs Benchmark", "template": "plotly_dark"}},
        "trades": {"data": [{"x": [item["ts"] for item in trades], "y": [item["to"] for item in trades], "text": [f'{item["asset"]}: {item["from"]} → {item["to"]}' for item in trades], "type": "scatter", "mode": "markers", "name": "Trades", "marker": {"size": 9, "symbol": ["triangle-up" if float(item["to"]) > float(item["from"]) else "triangle-down" for item in trades]}}], "layout": {"title": "Trade Details", "template": "plotly_dark"}},
        "positions": {"data": position_data, "layout": {"title": "Position Changes", "template": "plotly_dark", "yaxis": {"title": "Weight"}}},
    }


def run_vectorbt(spec: dict[str, Any], window: dict[str, list[dict]], *, initial_cash: float = 100_000.0, logger: Any | None = None) -> dict:
    t0 = time.monotonic()
    native = _run_native_vectorbt(spec, window, initial_cash=initial_cash, logger=logger)
    if native is not None:
        return native
    assets = [str(item).upper() for item in spec.get("assets", [])]
    fast = max(2, int(spec.get("fast_window", 12)))
    slow = max(fast + 1, int(spec.get("slow_window", 26)))
    fee_bps = max(0.0, float(spec.get("fee_bps", 10.0)))
    cost_bps = fee_bps + max(0.0, float(spec.get("slippage_bps", 0.0)))
    signal = str(spec.get("signal", "momentum"))
    threshold = float(spec.get("entry_threshold", 0.0))
    long_short = bool(spec.get("long_short", False))
    bars_by_asset = {
        asset: [row for row in window.get(asset, []) if float(row.get("close", 0)) > 0]
        for asset in assets
    }
    # A signal is evaluated from bar 1 onward; report progress against the
    # actual number of evaluations so the final update always reaches 100%.
    total_bars = sum(max(0, len(bars) - 1) for bars in bars_by_asset.values())
    if logger:
        for asset in assets:
            bars = bars_by_asset[asset]
            logger.data_loaded(asset, len(bars), (spec.get("data_sources") or {}).get(asset, "store"))
    series: list[tuple[datetime, float, float]] = []
    trades: list[dict] = []
    positions: list[dict] = []
    all_returns: list[float] = []
    global_bar = 0
    adjusted = False
    for asset in assets:
        bars = bars_by_asset[asset]
        if len(bars) < 4:
            raise ValueError(f"insufficient candle history for {asset}")
        # The requested MA/breakout windows may exceed the loaded history on
        # short ranges (1 day / 1 week / 1 month). Clamp the windows to the
        # available bars so the backtest still runs with a feasible signal.
        slow_effective = min(slow, max(3, len(bars) - 2))
        fast_effective = min(fast, max(2, slow_effective - 1))
        if slow_effective != slow or fast_effective != fast:
            adjusted = True
        closes = [float(row["close"]) for row in bars]
        previous = 0.0
        # The signal at ``index`` only sees closes strictly before that bar.
        # The resulting position is applied to the following bar, preventing
        # same-bar execution / look-ahead bias in the compatible engine.
        equity_sofar = initial_cash
        for index in range(1, len(bars)):
            target = _signal(closes, index, fast_effective, slow_effective, signal, threshold, long_short)
            change = target - previous
            asset_return = closes[index] / closes[index - 1] - 1
            period_return = previous * asset_return - abs(change) * cost_bps / 10_000
            all_returns.append(period_return)
            equity_sofar *= 1 + period_return
            series.append((bars[index]["ts"], period_return, asset_return))
            positions.append({"ts": bars[index]["ts"].isoformat(), "asset": asset, "weight": round(target, 6)})
            if change:
                direction = "buy" if target > previous else "sell"
                trades.append({"ts": bars[index]["ts"].isoformat(), "asset": asset, "from": previous, "to": target, "turnover": abs(change)})
                if logger:
                    logger.trade(asset, bars[index]["ts"], direction, closes[index], target, equity_sofar)
            previous = target
            global_bar += 1
            if logger and (global_bar % PROGRESS_INTERVAL_BARS == 0 or global_bar == total_bars):
                logger.progress(global_bar, total_bars, asset, closes[index], equity_sofar)
    series.sort(key=lambda item: item[0])
    equity = []
    value = 1.0
    for ts, period_return, _ in series:
        value *= 1 + period_return
        equity.append({"ts": ts.isoformat(), "equity": round(value * initial_cash, 6)})
    metrics = enrich_metrics(calculate_metrics(all_returns), all_returns)
    metrics.update({"trade_count": len(trades), "turnover": round(sum(item["turnover"] for item in trades), 6), "exposure_time": round(sum(abs(item["weight"]) for item in positions) / len(positions), 6) if positions else 0.0, "initial_cash": initial_cash, "final_equity": round(value * initial_cash, 6)})
    benchmark_by_ts: dict[str, list[float]] = {}
    for ts, _, asset_return in series:
        benchmark_by_ts.setdefault(ts.isoformat(), []).append(asset_return)
    benchmark_value = initial_cash
    benchmark = []
    for ts in sorted(benchmark_by_ts):
        benchmark_value *= 1 + sum(benchmark_by_ts[ts]) / len(benchmark_by_ts[ts])
        benchmark.append({"ts": ts, "equity": round(benchmark_value, 6)})
    drawdown = _drawdown_curve(equity)
    result = {"metrics": metrics, "equity_curve": equity, "drawdown_curve": drawdown, "benchmark_curve": benchmark, "trades": trades, "positions": positions, "charts": _charts(equity, drawdown, benchmark, trades, positions), "engine": "vectorbt" if _vectorbt_available() else "vectorbt_compatible", "is_live": False}
    if adjusted:
        result["windows_adjusted"] = {"fast": fast_effective, "slow": slow_effective}
    if logger:
        _log_summary_metrics(logger, metrics)
        ret = metrics.get("total_return", 0.0)
        logger.complete(len(trades), metrics.get("final_equity", 0.0), ret, int((time.monotonic() - t0) * 1000))
    return result


def _run_native_vectorbt(spec: dict[str, Any], window: dict[str, list[dict]], *, initial_cash: float, logger: Any | None = None) -> dict[str, Any] | None:
    """Use native VectorBT for the simple single-asset path when dependencies exist."""
    assets = [str(item).upper() for item in spec.get("assets", [])]
    if len(assets) != 1:
        return None
    t0 = time.monotonic()
    try:
        import numpy as np
        import pandas as pd
        import vectorbt as vbt

        rows = [row for row in window.get(assets[0], []) if float(row.get("close", 0)) > 0]
        fast = max(2, int(spec.get("fast_window", 12)))
        slow = max(fast + 1, int(spec.get("slow_window", 26)))
        if len(rows) < slow + 2:
            if logger:
                logger.warning(f"insufficient candle history for native {assets[0]} ({len(rows)} bars, need {slow + 2})")
            return None
        if logger:
            logger.data_loaded(assets[0], len(rows), (spec.get("data_sources") or {}).get(assets[0], "store"))
        close = pd.Series([float(row["close"]) for row in rows], index=pd.to_datetime([row["ts"] for row in rows]))
        fast_ma = close.rolling(fast).mean()
        slow_ma = close.rolling(slow).mean()
        # VectorBT fills at the close of the signal bar by default. Shift the
        # signal one bar to preserve the same no-look-ahead contract as the
        # pure-Python engine.
        entries = (fast_ma > slow_ma).shift(1, fill_value=False)
        exits = (fast_ma <= slow_ma).shift(1, fill_value=False)
        cost_bps = max(0.0, float(spec.get("fee_bps", 10.0))) + max(
            0.0, float(spec.get("slippage_bps", 0.0))
        )
        pf = vbt.Portfolio.from_signals(
            close, entries, exits, init_cash=initial_cash, fees=cost_bps / 10_000
        )
        values = pf.value()
        returns = [float(item) for item in pf.returns().fillna(0).tolist()]
        metrics = enrich_metrics(calculate_metrics(returns), returns)
        metrics.update({"trade_count": int(pf.trades.count()), "initial_cash": initial_cash, "final_equity": float(values.iloc[-1])})
        equity = [{"ts": index.isoformat(), "equity": round(float(value), 6)} for index, value in values.items()]
        benchmark = [{"ts": index.isoformat(), "equity": round(float(value / close.iloc[0] * initial_cash), 6)} for index, value in close.items()]
        positions = []
        trades = []
        previous = 0.0
        total_bars = len(close)
        for bar_idx, (index, entry, exit, price, eq_val) in enumerate(zip(close.index, entries, exits, close.values, values.values)):
            target = 1.0 if entry else 0.0 if exit else previous
            ts = index.isoformat()
            positions.append({"ts": ts, "asset": assets[0], "weight": target})
            if target != previous:
                direction = "buy" if target > previous else "sell"
                trades.append({"ts": ts, "asset": assets[0], "from": previous, "to": target, "turnover": abs(target - previous)})
                if logger:
                    logger.trade(assets[0], ts, direction, price, target, eq_val)
            previous = target
            completed = bar_idx + 1
            if logger and (completed % PROGRESS_INTERVAL_BARS == 0 or completed == total_bars):
                logger.progress(completed, total_bars, assets[0], price, eq_val)
        drawdown = _drawdown_curve(equity)
        result = {"metrics": metrics, "equity_curve": equity, "drawdown_curve": drawdown, "benchmark_curve": benchmark, "trades": trades, "positions": positions, "charts": _charts(equity, drawdown, benchmark, trades, positions), "engine": "vectorbt", "is_live": False}
        if logger:
            _log_summary_metrics(logger, metrics)
            ret = metrics.get("total_return", 0.0)
            logger.complete(len(trades), metrics.get("final_equity", 0.0), ret, int((time.monotonic() - t0) * 1000))
        return result
    except (ImportError, ValueError, TypeError, AttributeError, KeyError):
        return None


def _vectorbt_available() -> bool:
    try:
        import vectorbt  # noqa: F401
        return True
    except ImportError:
        return False
