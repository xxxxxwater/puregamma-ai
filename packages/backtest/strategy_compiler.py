from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from packages.backtest.strategy_spec import SUPPORTED_CRYPTO_ASSETS, parse_spec
from packages.trading.schemas.strategy_specs import ExecutableStrategySpec


class StrategyCompilationError(ValueError):
    pass


def _instrument_for_asset(asset: str) -> str:
    normalized = asset.upper().strip()
    if normalized in SUPPORTED_CRYPTO_ASSETS:
        return f"{normalized}USDT"
    return normalized


def _entry_rules(spec) -> list[dict[str, Any]]:
    base = {
        "fast_window": spec.fast_window,
        "slow_window": spec.slow_window,
        "threshold": float(spec.entry_threshold),
        "execution_timing": "next_bar_close",
        "lookahead_guard": "signals executed on next bar close",
    }
    if spec.signal == "momentum":
        return [
            {
                **base,
                "type": "momentum",
                "condition": "fast_window_return_above_slow_window_return",
            }
        ]
    if spec.signal == "breakout":
        return [
            {
                **base,
                "type": "breakout",
                "condition": "close_breaks_recent_range",
            }
        ]
    if spec.signal == "mean_reversion":
        return [
            {
                **base,
                "type": "mean_reversion",
                "condition": "fast_window_deviation_reverts_to_slow_window",
            }
        ]
    raise StrategyCompilationError(
        f"{spec.signal} is not supported by the phase 1 executable compiler"
    )


def _exit_rules(spec) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = [
        {
            "type": "signal_flip",
            "threshold": float(spec.exit_threshold),
            "execution_timing": "next_bar_close",
        }
    ]
    if spec.stop_loss_pct is not None:
        rules.append({"type": "stop_loss", "stop_loss_pct": float(spec.stop_loss_pct)})
    return rules


def compile_backtest_spec(
    payload: dict[str, Any],
    *,
    assumptions: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    window_days: int | None = None,
    execution_mode: str = "PAPER",
    version: int = 1,
    created_by: str = "",
) -> ExecutableStrategySpec:
    """Compile the research backtest contract into the runtime contract.

    Only phase-1 daily directional strategies are executable. Future strategy
    families are intentionally rejected here until their risk/order semantics
    are implemented end to end.
    """

    try:
        spec = parse_spec(payload)
    except Exception as exc:
        raise StrategyCompilationError(f"Backtest spec is invalid: {exc}") from exc
    if spec.mode != "daily":
        raise StrategyCompilationError(
            "Only daily DirectionalStrategy backtests can be saved as executable strategies in phase 1"
        )
    if not spec.assets:
        raise StrategyCompilationError("At least one asset is required")

    assumptions = assumptions or {}
    result = result or {}
    metrics = result.get("metrics") or {}
    sample_end = assumptions.get("sample_end")
    try:
        data_cutoff_time = (
            datetime.fromisoformat(sample_end)
            if isinstance(sample_end, str) and sample_end
            else datetime.now(timezone.utc)
        )
    except ValueError:
        data_cutoff_time = datetime.now(timezone.utc)

    instruments = [_instrument_for_asset(asset) for asset in spec.assets]
    fee_bps = float(assumptions.get("fee_bps", spec.fee_bps))
    slippage_bps = float(assumptions.get("slippage_bps", spec.slippage_bps))
    stop_loss = float(spec.stop_loss_pct) if spec.stop_loss_pct is not None else 0.03
    max_drawdown = max(0.05, min(0.5, float(abs(metrics.get("max_drawdown", 0.1)))))
    max_notional = 10_000.0
    max_daily_loss = max(100.0, max_notional * min(max_drawdown, 0.2))
    risk_policy = {
        "max_position": float(spec.max_position),
        "max_notional": max_notional,
        "max_leverage": 1.0,
        "max_daily_loss": max_daily_loss,
        "max_drawdown": max_drawdown,
        "max_orders_per_minute": 5,
        "reduce_only": False,
        "pause_opening": False,
        "global_kill_switch": False,
        "stale_market_blocks_opening": True,
        "stale_account_blocks_opening": True,
        "unknown_order_blocks_opening": True,
        "reconciliation_required_blocks_opening": True,
    }
    direction = "LONG_SHORT" if spec.long_short else "LONG_ONLY"
    raw = {
        "name": spec.name,
        "description": spec.thesis
        or f"Compiled from {spec.signal} backtest for {', '.join(spec.assets)}",
        "version": version,
        "instruments": instruments,
        "venues": ["MOCK"],
        "timeframe": "1d",
        "strategy_type": "DirectionalStrategy",
        "strategy_subtype": "cta_trend"
        if spec.signal in {"momentum", "breakout"}
        else spec.signal,
        "entry_rules": _entry_rules(spec),
        "exit_rules": _exit_rules(spec),
        "filters": [
            {
                "type": "data_freshness",
                "max_age_seconds": 300,
                "action": "block_new_opening_orders",
            }
        ],
        "feature_sources": ["market"],
        "sentiment_sources": [],
        "position_sizing": {
            "method": "fractional_notional",
            "max_fraction": float(spec.max_position),
            "direction": direction,
            "rebalance_days": int(spec.rebalance_days),
        },
        "risk_policy": risk_policy,
        "output_contract": "OrderIntent",
        "order_intent_template": {
            "contract_type": "OrderIntent",
            "instrument": "{instrument}",
            "venue": "MOCK",
            "side": "{side}",
            "notional": "{bounded_notional}",
            "order_type": "MARKET",
            "reduce_only": False,
        },
        "activation_supported": True,
        "activation_phase": 1,
        "max_position": float(spec.max_position),
        "max_notional": max_notional,
        "leverage": 1.0,
        "stop_loss": stop_loss,
        "take_profit": None,
        "max_daily_loss": max_daily_loss,
        "max_drawdown": max_drawdown,
        "max_orders_per_minute": 5,
        "order_type": "MARKET",
        "reduce_only": False,
        "execution_mode": execution_mode,
        "backtest_config": {
            "source": "unified_backtest",
            "original_spec": spec.model_dump(mode="json"),
            "lookback_days": window_days,
            "fee_bps": fee_bps,
            "slippage_bps": slippage_bps,
            "sample_start": assumptions.get("sample_start"),
            "sample_end": assumptions.get("sample_end"),
            "data_source": assumptions.get("data_source"),
            "lookahead_guard": assumptions.get(
                "lookahead_guard", "signals executed on next bar close"
            ),
        },
        "model_version": "rules-v1",
        "runtime_contract_version": "strategy-runtime-v1",
        "data_cutoff_time": data_cutoff_time,
        "created_by": created_by,
    }
    try:
        return ExecutableStrategySpec.model_validate(raw)
    except ValidationError as exc:
        raise StrategyCompilationError(str(exc)) from exc
