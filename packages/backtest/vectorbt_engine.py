"""Small VectorBT-compatible research engine.

VectorBT is used when installed in production. The pure-Python path keeps local
and test environments functional while preserving the same result contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from packages.backtest.metrics import calculate_metrics
from packages.backtest.quantstats_adapter import enrich_metrics


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


def run_vectorbt(spec: dict[str, Any], window: dict[str, list[dict]], *, initial_cash: float = 100_000.0) -> dict:
    native = _run_native_vectorbt(spec, window, initial_cash=initial_cash)
    if native is not None:
        return native
    assets = [str(item).upper() for item in spec.get("assets", [])]
    fast = max(2, int(spec.get("fast_window", 12)))
    slow = max(fast + 1, int(spec.get("slow_window", 26)))
    fee_bps = max(0.0, float(spec.get("fee_bps", 10.0)))
    signal = str(spec.get("signal", "momentum"))
    threshold = float(spec.get("entry_threshold", 0.0))
    long_short = bool(spec.get("long_short", False))
    series: list[tuple[datetime, float]] = []
    trades: list[dict] = []
    positions: list[dict] = []
    all_returns: list[float] = []
    for asset in assets:
        bars = [row for row in window.get(asset, []) if float(row.get("close", 0)) > 0]
        if len(bars) < slow + 2:
            raise ValueError(f"insufficient candle history for {asset}")
        closes = [float(row["close"]) for row in bars]
        previous = 0.0
        for index in range(1, len(bars)):
            target = _signal(closes, index, fast, slow, signal, threshold, long_short)
            change = target - previous
            asset_return = closes[index] / closes[index - 1] - 1
            period_return = previous * asset_return - abs(change) * fee_bps / 10_000
            all_returns.append(period_return)
            series.append((bars[index]["ts"], period_return))
            positions.append({"ts": bars[index]["ts"].isoformat(), "asset": asset, "weight": round(target, 6)})
            if change:
                trades.append({"ts": bars[index]["ts"].isoformat(), "asset": asset, "from": previous, "to": target, "turnover": abs(change)})
            previous = target
    series.sort(key=lambda item: item[0])
    equity = []
    value = 1.0
    for ts, period_return in series:
        value *= 1 + period_return
        equity.append({"ts": ts.isoformat(), "equity": round(value * initial_cash, 6)})
    metrics = enrich_metrics(calculate_metrics(all_returns), all_returns)
    metrics.update({"trade_count": len(trades), "turnover": round(sum(item["turnover"] for item in trades), 6), "exposure_time": round(sum(abs(item["weight"]) for item in positions) / len(positions), 6) if positions else 0.0, "initial_cash": initial_cash, "final_equity": round(value * initial_cash, 6)})
    peak = 0.0
    drawdown = []
    for item in equity:
        peak = max(peak, item["equity"])
        drawdown.append({"ts": item["ts"], "drawdown": round(item["equity"] / peak - 1, 8) if peak else 0.0})
    charts = {
        "equity": {"data": [{"x": [item["ts"] for item in equity], "y": [item["equity"] for item in equity], "type": "scatter", "mode": "lines", "name": "Strategy"}], "layout": {"title": "Equity Curve", "template": "plotly_dark"}},
        "drawdown": {"data": [{"x": [item["ts"] for item in drawdown], "y": [item["drawdown"] for item in drawdown], "type": "scatter", "mode": "lines", "fill": "tozeroy", "name": "Drawdown"}], "layout": {"title": "Drawdown", "template": "plotly_dark"}},
    }
    return {"metrics": metrics, "equity_curve": equity, "drawdown_curve": drawdown, "trades": trades, "positions": positions, "charts": charts, "engine": "vectorbt" if _vectorbt_available() else "vectorbt_compatible", "is_live": False}


def _run_native_vectorbt(spec: dict[str, Any], window: dict[str, list[dict]], *, initial_cash: float) -> dict[str, Any] | None:
    """Use native VectorBT for the simple single-asset path when dependencies exist."""
    assets = [str(item).upper() for item in spec.get("assets", [])]
    if len(assets) != 1:
        return None
    try:
        import numpy as np
        import pandas as pd
        import vectorbt as vbt

        rows = [row for row in window.get(assets[0], []) if float(row.get("close", 0)) > 0]
        fast = max(2, int(spec.get("fast_window", 12)))
        slow = max(fast + 1, int(spec.get("slow_window", 26)))
        if len(rows) < slow + 2:
            return None
        close = pd.Series([float(row["close"]) for row in rows], index=pd.to_datetime([row["ts"] for row in rows]))
        fast_ma = close.rolling(fast).mean()
        slow_ma = close.rolling(slow).mean()
        entries = (fast_ma > slow_ma).fillna(False)
        exits = (fast_ma <= slow_ma).fillna(False)
        pf = vbt.Portfolio.from_signals(close, entries, exits, init_cash=initial_cash, fees=max(0.0, float(spec.get("fee_bps", 10.0))) / 10_000)
        values = pf.value()
        returns = [float(item) for item in pf.returns().fillna(0).tolist()]
        metrics = enrich_metrics(calculate_metrics(returns), returns)
        metrics.update({"trade_count": int(pf.trades.count()), "initial_cash": initial_cash, "final_equity": float(values.iloc[-1])})
        equity = [{"ts": index.isoformat(), "equity": round(float(value), 6)} for index, value in values.items()]
        peak = np.maximum.accumulate(values.to_numpy())
        drawdown = [{"ts": index.isoformat(), "drawdown": round(float(value / peak[i] - 1), 8)} for i, (index, value) in enumerate(values.items())]
        x = [item["ts"] for item in equity]
        return {"metrics": metrics, "equity_curve": equity, "drawdown_curve": drawdown, "trades": [], "positions": [], "charts": {"equity": {"data": [{"x": x, "y": [item["equity"] for item in equity], "type": "scatter", "mode": "lines", "name": "Strategy"}], "layout": {"title": "Equity Curve", "template": "plotly_dark"}}, "drawdown": {"data": [{"x": x, "y": [item["drawdown"] for item in drawdown], "type": "scatter", "mode": "lines", "fill": "tozeroy", "name": "Drawdown"}], "layout": {"title": "Drawdown", "template": "plotly_dark"}}}, "engine": "vectorbt", "is_live": False}
    except (ImportError, ValueError, TypeError, AttributeError, KeyError):
        return None


def _vectorbt_available() -> bool:
    try:
        import vectorbt  # noqa: F401
        return True
    except ImportError:
        return False
