from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any


def enrich_metrics(metrics: dict[str, Any], returns: list[float]) -> dict[str, Any]:
    """Use QuantStats when available; retain the stable local metrics contract otherwise."""
    enriched = dict(metrics)
    try:
        import pandas as pd
        import quantstats as qs

        series = pd.Series(
            returns,
            index=pd.date_range(end=datetime.now(timezone.utc), periods=len(returns), freq="D"),
            dtype=float,
        )
        values = {
            "cagr": float(qs.stats.cagr(series)) if returns else 0.0,
            "sortino": float(qs.stats.sortino(series)) if returns else 0.0,
            "calmar": float(qs.stats.calmar(series)) if returns else 0.0,
            "annual_volatility": float(qs.stats.volatility(series)) if returns else 0.0,
        }
        enriched.update({key: value if isfinite(value) else 0.0 for key, value in values.items()})
        enriched["analytics_engine"] = "quantstats"
    except (ImportError, ValueError, TypeError, ZeroDivisionError, AttributeError, IndexError, OverflowError):
        enriched.setdefault("cagr", enriched.get("total_return", 0.0))
        enriched.setdefault("sortino", enriched.get("sharpe", 0.0))
        enriched.setdefault("calmar", 0.0)
        enriched.setdefault("annual_volatility", 0.0)
        enriched["analytics_engine"] = "quantstats_compatible"
    return enriched
