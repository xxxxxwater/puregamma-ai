# Signal Confidence Framework

Signal confidence is not conviction. It is a quality score for whether the current evidence supports publishing a research signal.

## Inputs

- Raw signal strength
- Required data availability
- Data freshness
- Regime match
- Risk score
- Backtest quality
- Whether KOL sentiment is the only supporting input
- Liquidity and capacity constraints

## Caps

- Missing required data lowers confidence.
- `risk_high` caps confidence unless there is strong confirmation.
- `risk_extreme` caps confidence at low-confidence research language.
- Inactive regime caps confidence.
- KOL sentiment alone cannot produce high confidence.
- Mock or insufficient backtests cap confidence.
- Research-only and Do not launch strategies cannot emit actionable language.

## SignalSpec

The canonical schema is implemented in `packages/strategies/signal_spec.py` and mirrored in `config/strategy_specs.yaml`.

Required fields:

- `strategy_name`
- `asset_universe`
- `signal_type`
- `direction`
- `raw_score`
- `normalized_score`
- `confidence`
- `risk_score`
- `regime_filter`
- `entry_condition`
- `exit_condition`
- `invalidation`
- `data_freshness_requirement`
- `minimum_liquidity`
- `max_leverage_assumption`
- `timeframe`
- `source_data`
- `disclaimers`
