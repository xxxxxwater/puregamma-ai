from __future__ import annotations

from math import sqrt

from packages.risk.drawdown import max_drawdown


def calculate_metrics(returns: list[float]) -> dict:
    if not returns:
        return {
            "total_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "trade_count": 0,
            "turnover": 0.0,
            "exposure_time": 0.0,
            "tail_loss_95": 0.0,
        }
    total = 1.0
    for item in returns:
        total *= 1 + item
    avg = sum(returns) / len(returns)
    variance = sum((item - avg) ** 2 for item in returns) / len(returns)
    sharpe = (avg / sqrt(variance) * sqrt(365)) if variance else 0.0
    equity = []
    value = 1.0
    for item in returns:
        value *= 1 + item
        equity.append(value)
    return {
        "total_return": round(total - 1, 4),
        "sharpe": round(sharpe, 2),
        "max_drawdown": max_drawdown(equity),
        "win_rate": round(sum(1 for item in returns if item > 0) / len(returns), 4),
        "trade_count": sum(1 for item in returns if item != 0),
        "turnover": round(sum(abs(item) for item in returns), 4),
        "exposure_time": round(sum(1 for item in returns if item != 0) / len(returns), 4),
        "tail_loss_95": round(sorted(returns)[max(0, int(len(returns) * 0.05) - 1)], 4),
    }
