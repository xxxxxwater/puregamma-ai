"""Daily-frequency backtest engine for the backtest lab.

Execution contract follows the NautilusTrader strategy conventions:
- Bars arrive in ascending time order (``on_bar`` semantics).
- A signal for bar N is computed only from bars [0, N-1] (strictly no look-ahead);
  the resulting position earns bar N's close-to-close return.
- ``daily`` mode evaluates each instrument independently (trend/mean-reversion/breakout).
- ``cross_sectional`` mode ranks the universe each rebalance bar, goes long the
  stronger leg and short the weaker leg when ``long_short`` is enabled
  (market-neutral style), sized by ``max_position`` per leg.
- Fees are charged on position changes at ``fee_bps`` per unit turnover.

This is a research simulation consistent with the PureGamma Nautilus contract:
it reports hypothetical performance and never touches order execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from packages.backtest.metrics import calculate_metrics
from packages.backtest.strategy_spec import StrategySpec


@dataclass
class DailyBar:
    ts: datetime
    close: float


@dataclass
class EngineResult:
    metrics: dict
    equity_curve: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    daily_returns: list[float] = field(default_factory=list)


def _series(bars: list[dict]) -> list[DailyBar]:
    return [DailyBar(ts=row["ts"], close=float(row["close"])) for row in bars if float(row["close"]) > 0]


def _moving_average(values: list[float], window: int) -> float:
    return sum(values[-window:]) / window


def _daily_signal(spec: StrategySpec, history: list[float], fast: int | None = None, slow: int | None = None) -> float:
    """Target position in [-max_position, max_position] from trailing closes."""
    fast = fast or spec.fast_window
    slow = slow or spec.slow_window
    if len(history) < slow:
        return 0.0
    fast_avg = _moving_average(history, fast)
    slow_avg = _moving_average(history, slow)
    last = history[-1]
    if spec.signal == "momentum":
        spread = (fast_avg - slow_avg) / slow_avg if slow_avg else 0.0
        if spread > spec.entry_threshold:
            return spec.max_position
        if spec.long_short and spread < -spec.entry_threshold:
            return -spec.max_position
        return 0.0
    if spec.signal == "mean_reversion":
        deviation = (last - slow_avg) / slow_avg if slow_avg else 0.0
        if deviation < -spec.entry_threshold:
            return spec.max_position
        if deviation > spec.entry_threshold:
            return -spec.max_position if spec.long_short else 0.0
        return 0.0
    # breakout: long when the last close exceeds the trailing slow-window high
    window_high = max(history[-slow:])
    window_low = min(history[-slow:])
    if last >= window_high * (1 + spec.entry_threshold):
        return spec.max_position
    if spec.long_short and last <= window_low * (1 - spec.entry_threshold):
        return -spec.max_position
    return 0.0


def _effective_windows(spec: StrategySpec, min_count: int) -> tuple[int, int]:
    slow = min(spec.slow_window, max(3, min_count - 2))
    fast = min(spec.fast_window, max(2, slow - 1))
    return fast, slow


def _run_daily_asset(spec: StrategySpec, bars: list[DailyBar], min_count: int | None = None) -> EngineResult:
    fast, slow = _effective_windows(spec, min_count or len(bars))
    closes = [bar.close for bar in bars]
    returns: list[float] = []
    equity: list[dict] = []
    trades: list[dict] = []
    previous = 0.0
    value = 1.0
    peak_price = closes[0] if closes else 0.0
    stopped_until = -1
    for index in range(1, len(bars)):
        history = closes[:index]
        target = _daily_signal(spec, history, fast=fast, slow=slow)
        if spec.stop_loss_pct and previous != 0.0:
            if previous > 0:
                peak_price = max(peak_price, closes[index - 1])
                if closes[index - 1] <= peak_price * (1 - spec.stop_loss_pct):
                    target = 0.0
                    stopped_until = index + spec.rebalance_days
            elif closes[index - 1] >= peak_price * (1 + spec.stop_loss_pct):
                peak_price = min(peak_price, closes[index - 1]) if peak_price else closes[index - 1]
                target = 0.0
                stopped_until = index + spec.rebalance_days
        if index < stopped_until:
            target = 0.0
        change = target - previous
        if change:
            trades.append({"ts": bars[index].ts.isoformat(), "from": previous, "to": target})
        asset_return = closes[index] / closes[index - 1] - 1
        period_return = previous * asset_return - abs(change) * spec.fee_bps / 10_000
        returns.append(period_return)
        value *= 1 + period_return
        equity.append({"ts": bars[index].ts.isoformat(), "equity": round(value, 6)})
        previous = target
    metrics = calculate_metrics(returns)
    metrics["trade_count"] = len(trades)
    return EngineResult(metrics=metrics, equity_curve=equity, trades=trades, daily_returns=returns)


def _run_cross_sectional(spec: StrategySpec, universe: dict[str, list[DailyBar]], min_count: int | None = None) -> EngineResult:
    legs = sorted(universe)
    if len(legs) != 2:
        raise ValueError("cross_sectional mode requires exactly two assets")
    left, right = universe[legs[0]], universe[legs[1]]
    ts_left = {bar.ts: bar.close for bar in left}
    ts_right = {bar.ts: bar.close for bar in right}
    common_ts = sorted(set(ts_left) & set(ts_right))
    _, slow = _effective_windows(spec, min_count or len(common_ts))
    if len(common_ts) < slow + 2:
        return EngineResult(metrics=calculate_metrics([]))
    left_closes = [ts_left[ts] for ts in common_ts]
    right_closes = [ts_right[ts] for ts in common_ts]
    returns: list[float] = []
    equity: list[dict] = []
    trades: list[dict] = []
    value = 1.0
    previous_left = previous_right = 0.0
    for index in range(1, len(common_ts)):
        if index % spec.rebalance_days == 0 and index >= slow:
            left_momentum = left_closes[index - 1] / left_closes[index - 1 - slow] - 1
            right_momentum = right_closes[index - 1] / right_closes[index - 1 - slow] - 1
            spread = left_momentum - right_momentum
            if abs(spread) <= spec.exit_threshold:
                target_left = target_right = 0.0
            elif spread > spec.entry_threshold:
                target_left, target_right = spec.max_position, (-spec.max_position if spec.long_short else 0.0)
            else:
                target_left, target_right = (-spec.max_position if spec.long_short else 0.0), spec.max_position
        else:
            target_left, target_right = previous_left, previous_right
        left_return = left_closes[index] / left_closes[index - 1] - 1
        right_return = right_closes[index] / right_closes[index - 1] - 1
        turnover = abs(target_left - previous_left) + abs(target_right - previous_right)
        if turnover:
            trades.append({"ts": common_ts[index].isoformat(), legs[0]: target_left, legs[1]: target_right})
        period_return = previous_left * left_return + previous_right * right_return - turnover * spec.fee_bps / 10_000
        returns.append(period_return)
        value *= 1 + period_return
        equity.append({"ts": common_ts[index].isoformat(), "equity": round(value, 6)})
        previous_left, previous_right = target_left, target_right
    metrics = calculate_metrics(returns)
    metrics["trade_count"] = len(trades)
    return EngineResult(metrics=metrics, equity_curve=equity, trades=trades, daily_returns=returns)


def run_lab_backtest(spec: StrategySpec, window: dict[str, list[dict]]) -> EngineResult:
    """Execute a spec over the shared candle window and return performance."""
    # Short ranges (1 day / 1 week / 1 month) may hold fewer bars than the
    # requested MA window. Clamp slow_window to the loaded history so the
    # engine still produces a feasible signal instead of failing outright.
    bar_counts = [len(_series(window.get(asset, []))) for asset in spec.assets]
    if any(count < 4 for count in bar_counts):
        raise ValueError("insufficient candle history for the requested window")
    if spec.mode == "cross_sectional":
        universe = {asset: _series(window.get(asset, [])) for asset in spec.assets}
        return _run_cross_sectional(spec, universe, min_count=min(bar_counts))

    combined_returns: list[tuple[datetime, float]] = []
    equity: list[dict] = []
    trades: list[dict] = []
    per_asset_metrics: dict[str, dict] = {}
    for asset in spec.assets:
        bars = _series(window.get(asset, []))
        result = _run_daily_asset(spec, bars, min_count=min(bar_counts))
        per_asset_metrics[asset] = result.metrics
        trades.extend({**trade, "asset": asset} for trade in result.trades)
        combined_returns.extend((bars[index + 1].ts, value) for index, value in enumerate(result.daily_returns))
    combined_returns.sort(key=lambda item: item[0])
    returns = [value for _, value in combined_returns]
    metrics = calculate_metrics(returns)
    metrics["trade_count"] = len(trades)
    metrics["per_asset"] = per_asset_metrics
    value = 1.0
    for ts, period_return in combined_returns:
        value *= 1 + period_return
        equity.append({"ts": ts.isoformat(), "equity": round(value, 6)})
    return EngineResult(metrics=metrics, equity_curve=equity, trades=trades, daily_returns=returns)


def downsample_equity(curve: list[dict], max_points: int = 400) -> list[dict]:
    if len(curve) <= max_points:
        return curve
    step = len(curve) / max_points
    sampled = [curve[int(i * step)] for i in range(max_points)]
    if curve[-1] is not sampled[-1]:
        sampled.append(curve[-1])
    return sampled
