from __future__ import annotations


def max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak:
            worst = min(worst, (value - peak) / peak)
    return round(worst, 4)
