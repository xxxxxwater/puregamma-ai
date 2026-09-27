"""Strategy-family research kernel used by Dream-RSI.

Signals are deterministic and causal: a position for interval N is computed
only from bars ending before interval N. Families advertise the factors they
need and their factor quality so unsupported research fails closed.
"""
from __future__ import annotations

from math import sqrt
from typing import Any

from packages.backtest.metrics import calculate_metrics
from packages.nautilus.data_adapter import timeframe_minutes


FAMILY_ORDER = (
    "momentum",
    "vwap",
    "orderflow",
    "funding_oi",
    "mean_reversion",
    "hybrid",
)

FAMILY_LABELS = {
    "momentum": "Momentum",
    "vwap": "VWAP",
    "orderflow": "Orderflow",
    "funding_oi": "Funding + OI",
    "mean_reversion": "Mean Reversion",
    "hybrid": "Hybrid",
}

FAMILY_FACTOR_QUALITY = {
    "momentum": "observed_close",
    "vwap": "rolling_24h_volume_proxy",
    "orderflow": "signed_volume_quote_proxy",
    "funding_oi": "public_perpetual_snapshot",
    "mean_reversion": "observed_close",
    "hybrid": "mixed_price_volume_proxy",
}


def family_candidate_library() -> dict[str, list[dict[str, Any]]]:
    return {
        "momentum": [
            {"family": "momentum", "factor_variant": "ma_cross", "fast_window": 6, "slow_window": 24, "fee_bps": 5.0},
            {"family": "momentum", "factor_variant": "ma_cross", "fast_window": 8, "slow_window": 32, "fee_bps": 5.0},
            {"family": "momentum", "factor_variant": "breakout", "lookback_window": 20, "buffer_bps": 5.0, "fee_bps": 5.0},
            {"family": "momentum", "factor_variant": "breakout", "lookback_window": 36, "buffer_bps": 10.0, "fee_bps": 7.5},
            {"family": "momentum", "factor_variant": "ma_cross", "fast_window": 12, "slow_window": 48, "fee_bps": 7.5},
        ],
        "vwap": [
            {"family": "vwap", "factor_variant": "vwap_reclaim", "vwap_window": 24, "band_bps": 5.0, "fee_bps": 5.0},
            {"family": "vwap", "factor_variant": "vwap_reclaim", "vwap_window": 48, "band_bps": 10.0, "fee_bps": 5.0},
            {"family": "vwap", "factor_variant": "vwap_deviation_trend", "vwap_window": 32, "band_bps": 20.0, "fee_bps": 7.5},
            {"family": "vwap", "factor_variant": "vwap_deviation_trend", "vwap_window": 64, "band_bps": 35.0, "fee_bps": 7.5},
        ],
        "orderflow": [
            {"family": "orderflow", "factor_variant": "signed_volume_pressure", "pressure_window": 12, "pressure_threshold": 0.08, "fee_bps": 7.5},
            {"family": "orderflow", "factor_variant": "signed_volume_pressure", "pressure_window": 24, "pressure_threshold": 0.12, "fee_bps": 7.5},
            {"family": "orderflow", "factor_variant": "spread_filtered_pressure", "pressure_window": 12, "pressure_threshold": 0.06, "max_spread_bps": 12.0, "fee_bps": 7.5},
            {"family": "orderflow", "factor_variant": "spread_filtered_pressure", "pressure_window": 24, "pressure_threshold": 0.10, "max_spread_bps": 20.0, "fee_bps": 10.0},
        ],
        "funding_oi": [
            {"family": "funding_oi", "factor_variant": "oi_trend_funding_filter", "oi_window": 8, "oi_change_threshold": 0.01, "funding_ceiling": 0.00025, "momentum_window": 8, "fee_bps": 7.5},
            {"family": "funding_oi", "factor_variant": "oi_trend_funding_filter", "oi_window": 16, "oi_change_threshold": 0.02, "funding_ceiling": 0.00015, "momentum_window": 12, "fee_bps": 7.5},
            {"family": "funding_oi", "factor_variant": "short_crowding_reversal", "oi_window": 8, "oi_change_threshold": 0.01, "funding_floor": -0.00005, "momentum_window": 8, "fee_bps": 10.0},
            {"family": "funding_oi", "factor_variant": "short_crowding_reversal", "oi_window": 16, "oi_change_threshold": 0.015, "funding_floor": -0.00010, "momentum_window": 12, "fee_bps": 10.0},
        ],
        "mean_reversion": [
            {"family": "mean_reversion", "factor_variant": "zscore_reversion", "mean_window": 24, "entry_z": 1.5, "exit_z": 0.25, "fee_bps": 5.0},
            {"family": "mean_reversion", "factor_variant": "zscore_reversion", "mean_window": 36, "entry_z": 1.75, "exit_z": 0.25, "fee_bps": 5.0},
            {"family": "mean_reversion", "factor_variant": "zscore_reversion", "mean_window": 48, "entry_z": 2.0, "exit_z": 0.50, "fee_bps": 7.5},
            {"family": "mean_reversion", "factor_variant": "zscore_reversion", "mean_window": 64, "entry_z": 2.25, "exit_z": 0.50, "fee_bps": 7.5},
        ],
        "hybrid": [
            {"family": "hybrid", "factor_variant": "momentum_vwap_confirm", "fast_window": 6, "slow_window": 24, "vwap_window": 24, "band_bps": 5.0, "fee_bps": 7.5},
            {"family": "hybrid", "factor_variant": "momentum_vwap_confirm", "fast_window": 8, "slow_window": 32, "vwap_window": 48, "band_bps": 10.0, "fee_bps": 7.5},
            {"family": "hybrid", "factor_variant": "momentum_orderflow_confirm", "fast_window": 6, "slow_window": 24, "pressure_window": 12, "pressure_threshold": 0.06, "fee_bps": 10.0},
            {"family": "hybrid", "factor_variant": "momentum_orderflow_confirm", "fast_window": 8, "slow_window": 36, "pressure_window": 24, "pressure_threshold": 0.10, "fee_bps": 10.0},
        ],
    }


def initial_family_candidates() -> list[dict[str, Any]]:
    library = family_candidate_library()
    return [dict(library[family][0]) for family in FAMILY_ORDER]


def candidate_key(candidate: dict[str, Any]) -> tuple:
    ignored = {"lookback_days", "timeframe"}
    return tuple(sorted((key, str(value)) for key, value in candidate.items() if key not in ignored))


def candidate_warmup(candidate: dict[str, Any]) -> int:
    numeric_keys = (
        "slow_window", "lookback_window", "vwap_window", "pressure_window",
        "oi_window", "momentum_window", "mean_window",
    )
    return max([int(candidate.get(key, 0) or 0) for key in numeric_keys] + [12])


def max_candidate_warmup(candidates: list[dict[str, Any]]) -> int:
    return max((candidate_warmup(candidate) for candidate in candidates), default=24)


def required_factors(candidate: dict[str, Any]) -> tuple[str, ...]:
    family = str(candidate.get("family") or "")
    variant = str(candidate.get("factor_variant") or "")
    if family == "vwap":
        return ("close", "volume")
    if family == "orderflow":
        return ("close", "volume", "bid_ask") if variant == "spread_filtered_pressure" else ("close", "volume")
    if family == "funding_oi":
        return ("close", "funding_rate", "open_interest")
    if family == "hybrid":
        return ("close", "volume")
    return ("close",)


def _factor_present(bar: dict[str, Any], factor: str) -> bool:
    if factor == "close":
        return float(bar.get("close") or 0.0) > 0
    if factor == "volume":
        return float(bar.get("volume") or 0.0) > 0
    if factor == "bid_ask":
        bid = float(bar.get("bid") or 0.0)
        ask = float(bar.get("ask") or 0.0)
        return bid > 0 and ask >= bid
    if factor == "funding_rate":
        return bar.get("funding_rate") is not None
    if factor == "open_interest":
        return float(bar.get("open_interest") or 0.0) > 0
    return False


def candidate_factor_coverage(bars: list[dict[str, Any]], candidate: dict[str, Any]) -> dict[str, float]:
    if not bars:
        return {factor: 0.0 for factor in required_factors(candidate)}
    return {
        factor: round(sum(1 for bar in bars if _factor_present(bar, factor)) / len(bars), 4)
        for factor in required_factors(candidate)
    }


def factor_quality(candidate: dict[str, Any]) -> str:
    return FAMILY_FACTOR_QUALITY.get(str(candidate.get("family") or ""), "unknown")


def _closes(bars: list[dict[str, Any]], start: int, end: int) -> list[float]:
    return [float(bar["close"]) for bar in bars[start:end]]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    avg = _mean(values)
    return sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def _momentum_condition(bars: list[dict[str, Any]], index: int, candidate: dict[str, Any]) -> bool:
    variant = str(candidate.get("factor_variant") or "ma_cross")
    if variant == "breakout":
        lookback = max(3, int(candidate.get("lookback_window", 20)))
        if index < lookback + 1:
            return False
        latest_close = float(bars[index - 1]["close"])
        prior_high = max(float(bar.get("high") or bar["close"]) for bar in bars[index - lookback - 1:index - 1])
        return latest_close > prior_high * (1.0 + float(candidate.get("buffer_bps", 0.0)) / 10_000)
    fast = max(2, int(candidate.get("fast_window", 6)))
    slow = max(fast + 1, int(candidate.get("slow_window", 24)))
    if index < slow:
        return False
    window = _closes(bars, index - slow, index)
    return _mean(window[-fast:]) > _mean(window)


def _vwap_value(bars: list[dict[str, Any]], index: int, window: int) -> float | None:
    if index < window:
        return None
    sample = bars[index - window:index]
    denominator = sum(float(bar.get("volume") or 0.0) for bar in sample)
    if denominator <= 0:
        return None
    return sum(float(bar["close"]) * float(bar.get("volume") or 0.0) for bar in sample) / denominator


def _vwap_condition(bars: list[dict[str, Any]], index: int, candidate: dict[str, Any]) -> bool:
    window = max(3, int(candidate.get("vwap_window", 24)))
    value = _vwap_value(bars, index, window)
    if value is None:
        return False
    latest = float(bars[index - 1]["close"])
    band = float(candidate.get("band_bps", 0.0)) / 10_000
    return latest >= value * (1.0 + band)


def _signed_volume_pressure(bars: list[dict[str, Any]], index: int, window: int) -> float | None:
    if index < window + 1:
        return None
    signed = total = 0.0
    for offset in range(index - window, index):
        current = float(bars[offset]["close"])
        previous = float(bars[offset - 1]["close"])
        volume = float(bars[offset].get("volume") or 0.0)
        if volume <= 0:
            continue
        signed += (1.0 if current > previous else -1.0 if current < previous else 0.0) * volume
        total += volume
    return signed / total if total > 0 else None


def _orderflow_condition(bars: list[dict[str, Any]], index: int, candidate: dict[str, Any]) -> bool:
    window = max(3, int(candidate.get("pressure_window", 12)))
    pressure = _signed_volume_pressure(bars, index, window)
    if pressure is None or pressure <= float(candidate.get("pressure_threshold", 0.08)):
        return False
    if str(candidate.get("factor_variant") or "") == "spread_filtered_pressure":
        last = bars[index - 1]
        bid = float(last.get("bid") or 0.0)
        ask = float(last.get("ask") or 0.0)
        if bid <= 0 or ask < bid:
            return False
        mid = (bid + ask) / 2.0
        spread_bps = ((ask - bid) / mid * 10_000) if mid > 0 else 1e9
        return spread_bps <= float(candidate.get("max_spread_bps", 20.0))
    return True


def _funding_oi_condition(bars: list[dict[str, Any]], index: int, candidate: dict[str, Any]) -> bool:
    oi_window = max(2, int(candidate.get("oi_window", 8)))
    momentum_window = max(2, int(candidate.get("momentum_window", 8)))
    required = max(oi_window, momentum_window)
    if index < required + 1:
        return False
    latest = bars[index - 1]
    old = bars[index - 1 - oi_window]
    funding = latest.get("funding_rate")
    latest_oi = float(latest.get("open_interest") or 0.0)
    old_oi = float(old.get("open_interest") or 0.0)
    if funding is None or latest_oi <= 0 or old_oi <= 0:
        return False
    oi_change = latest_oi / old_oi - 1.0
    latest_close = float(latest["close"])
    old_close = float(bars[index - 1 - momentum_window]["close"])
    momentum = latest_close / old_close - 1.0 if old_close > 0 else 0.0
    if str(candidate.get("factor_variant") or "") == "short_crowding_reversal":
        return (
            float(funding) <= float(candidate.get("funding_floor", -0.00005))
            and oi_change >= float(candidate.get("oi_change_threshold", 0.01))
            and momentum >= -0.01
        )
    return (
        float(funding) <= float(candidate.get("funding_ceiling", 0.00025))
        and oi_change >= float(candidate.get("oi_change_threshold", 0.01))
        and momentum > 0
    )


def _mean_reversion_position(bars: list[dict[str, Any]], index: int, candidate: dict[str, Any], previous_position: float) -> float:
    window = max(5, int(candidate.get("mean_window", 24)))
    if index < window:
        return 0.0
    sample = _closes(bars, index - window, index)
    std = _std(sample)
    if std <= 0:
        return 0.0
    zscore = (sample[-1] - _mean(sample)) / std
    entry = abs(float(candidate.get("entry_z", 1.5)))
    exit_z = abs(float(candidate.get("exit_z", 0.25)))
    if previous_position > 0:
        return 0.0 if zscore >= -exit_z else 1.0
    return 1.0 if zscore <= -entry else 0.0


def desired_position(bars: list[dict[str, Any]], index: int, candidate: dict[str, Any], previous_position: float) -> float:
    family = str(candidate.get("family") or "momentum")
    if family == "momentum":
        return 1.0 if _momentum_condition(bars, index, candidate) else 0.0
    if family == "vwap":
        return 1.0 if _vwap_condition(bars, index, candidate) else 0.0
    if family == "orderflow":
        return 1.0 if _orderflow_condition(bars, index, candidate) else 0.0
    if family == "funding_oi":
        return 1.0 if _funding_oi_condition(bars, index, candidate) else 0.0
    if family == "mean_reversion":
        return _mean_reversion_position(bars, index, candidate, previous_position)
    if family == "hybrid":
        momentum_candidate = {**candidate, "factor_variant": "ma_cross"}
        momentum_ok = _momentum_condition(bars, index, momentum_candidate)
        if str(candidate.get("factor_variant") or "") == "momentum_orderflow_confirm":
            return 1.0 if momentum_ok and _orderflow_condition(
                bars, index, {**candidate, "factor_variant": "signed_volume_pressure"}
            ) else 0.0
        return 1.0 if momentum_ok and _vwap_condition(
            bars, index, {**candidate, "factor_variant": "vwap_reclaim"}
        ) else 0.0
    return 0.0


def _segment_metrics(returns: list[float], positions: list[float], changes: list[float], periods_per_year: float) -> dict[str, Any]:
    metrics = calculate_metrics(returns, periods_per_year=periods_per_year)
    metrics["trade_count"] = sum(1 for change in changes if change > 0)
    metrics["turnover"] = round(sum(changes), 4)
    metrics["exposure_time"] = round(sum(positions) / len(positions), 4) if positions else 0.0
    return metrics


def evaluate_family_candidate(
    bars: list[dict[str, Any]],
    candidate: dict[str, Any],
    *,
    timeframe: str,
    split_index: int,
    minimum_factor_coverage: float = 0.70,
) -> dict[str, Any]:
    coverage = candidate_factor_coverage(bars, candidate)
    missing = [factor for factor, ratio in coverage.items() if ratio < minimum_factor_coverage]
    if missing:
        return {
            "available": False,
            "family": candidate.get("family"),
            "factor_variant": candidate.get("factor_variant"),
            "reason": "factor_unavailable",
            "missing_factors": missing,
            "factor_coverage": coverage,
            "factor_quality": factor_quality(candidate),
        }

    strategy_returns: list[float] = []
    positions: list[float] = []
    changes: list[float] = []
    previous_position = 0.0
    fee = max(0.0, float(candidate.get("fee_bps", 7.5))) / 10_000
    for index in range(1, len(bars)):
        position = desired_position(bars, index, candidate, previous_position)
        change = abs(position - previous_position)
        previous_close = float(bars[index - 1]["close"])
        current_close = float(bars[index]["close"])
        asset_return = current_close / previous_close - 1.0 if previous_close > 0 else 0.0
        strategy_returns.append(position * asset_return - change * fee)
        positions.append(position)
        changes.append(change)
        previous_position = position

    split_return = max(1, min(len(strategy_returns) - 1, split_index - 1))
    periods_per_year = 365.0 * 24.0 * 60.0 / timeframe_minutes(timeframe)
    in_sample = _segment_metrics(strategy_returns[:split_return], positions[:split_return], changes[:split_return], periods_per_year)
    out_of_sample = _segment_metrics(strategy_returns[split_return:], positions[split_return:], changes[split_return:], periods_per_year)
    return {
        "available": True,
        "family": candidate.get("family"),
        "factor_variant": candidate.get("factor_variant"),
        "params": dict(candidate),
        "total_return": out_of_sample.get("total_return", 0.0),
        "sharpe_ratio": out_of_sample.get("sharpe", 0.0),
        "max_drawdown": out_of_sample.get("max_drawdown", 0.0),
        "win_rate": out_of_sample.get("win_rate", 0.0),
        "trade_count": out_of_sample.get("trade_count", 0),
        "turnover": out_of_sample.get("turnover", 0.0),
        "in_sample": in_sample,
        "out_of_sample": out_of_sample,
        "factor_coverage": coverage,
        "factor_quality": factor_quality(candidate),
    }


def allocate_family_compute(
    nodes: list[dict[str, Any]],
    remaining: int,
    unavailable_families: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        family = str(node.get("family") or "")
        if family:
            by_family.setdefault(family, []).append(node)

    library = family_candidate_library()
    unavailable_names = {
        str(item.get("family")) for item in (unavailable_families or []) if item.get("family")
    }
    ranking: list[dict[str, Any]] = []
    seen_counts: dict[str, int] = {}
    for family in FAMILY_ORDER:
        rows = by_family.get(family, [])
        seen_counts[family] = len({candidate_key(dict(row.get("params") or {})) for row in rows})
        if not rows:
            continue
        best = max(rows, key=lambda row: float(row.get("score") or 0.0))
        ranking.append({
            "family": family,
            "label": FAMILY_LABELS[family],
            "best_score": float(best.get("score") or 0.0),
            "best_node_id": best.get("id"),
            "constraint_matches": sum(1 for row in rows if row.get("meets_constraints")),
            "observations": len(rows),
        })
    ranking.sort(key=lambda item: (item["constraint_matches"] > 0, item["best_score"]), reverse=True)

    capacity = {
        family: max(0, len(library.get(family, [])) - seen_counts.get(family, 0))
        for family in by_family if family not in unavailable_names
    }
    allocation = {family: 0 for family in FAMILY_ORDER}
    active = [item["family"] for item in ranking if capacity.get(item["family"], 0) > 0]
    slots = max(0, int(remaining))
    if slots >= len(active):
        for family in active:
            allocation[family] += 1
            capacity[family] -= 1
            slots -= 1

    total_rank = max(1, len(ranking))
    weights = {
        item["family"]: float(total_rank - rank)
        + (2.0 if item["constraint_matches"] else 0.0)
        + max(0.0, float(item["best_score"])) * 0.05
        for rank, item in enumerate(ranking)
    }
    while slots > 0:
        choices = [family for family in active if capacity.get(family, 0) > 0]
        if not choices:
            break
        family = max(
            choices,
            key=lambda name: (weights.get(name, 0.1) / (1.0 + allocation[name]), -FAMILY_ORDER.index(name)),
        )
        allocation[family] += 1
        capacity[family] -= 1
        slots -= 1

    return {
        "policy": "family_rank_with_exploration_floor_v1",
        "allocation": allocation,
        "ranking": ranking,
        "unavailable_families": list(unavailable_families or []),
        "basis": "OOS objective rank + constraint bonus + exploration floor + diminishing returns",
    }


def next_family_candidates(observed_nodes: list[dict[str, Any]], allocation: dict[str, int]) -> list[dict[str, Any]]:
    library = family_candidate_library()
    seen = {candidate_key(dict(node.get("params") or {})) for node in observed_nodes}
    selected: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        budget = max(0, int(allocation.get(family, 0)))
        for candidate in library.get(family, []):
            if budget <= 0:
                break
            if candidate_key(candidate) in seen:
                continue
            selected.append(dict(candidate))
            seen.add(candidate_key(candidate))
            budget -= 1
    return selected
