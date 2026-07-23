from __future__ import annotations

from typing import Any


def enrich_metrics(metrics: dict[str, Any], returns: list[float]) -> dict[str, Any]:
    """Use QuantStats when available; retain the stable local metrics contract otherwise."""
    enriched = dict(metrics)
    try:
        import quantstats as qs

        enriched["cagr"] = float(qs.stats.cagr(returns)) if returns else 0.0
        enriched["sortino"] = float(qs.stats.sortino(returns)) if returns else 0.0
        enriched["calmar"] = float(qs.stats.calmar(returns)) if returns else 0.0
        enriched["annual_volatility"] = float(qs.stats.volatility(returns)) if returns else 0.0
        enriched["analytics_engine"] = "quantstats"
    except (ImportError, ValueError, TypeError, ZeroDivisionError):
        enriched.setdefault("cagr", enriched.get("total_return", 0.0))
        enriched.setdefault("sortino", enriched.get("sharpe", 0.0))
        enriched.setdefault("calmar", 0.0)
        enriched.setdefault("annual_volatility", 0.0)
        enriched["analytics_engine"] = "quantstats_compatible"
    return enriched
