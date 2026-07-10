# PureGamma Strategy Research Framework

PureGamma strategies are research artifacts before they are signals. A strategy is eligible for product output only when its hypothesis, data lineage, signal formula, risk model, backtest assumptions, and invalidation path are explicit.

## Research Standard

Each strategy must define:

1. Economic rationale: why the edge could exist and who is on the other side.
2. Tradable universe: instruments, venues, quote currency, borrow/funding constraints, and market hours.
3. Signal inputs: OHLCV, funding, OI, liquidations, event timestamps, portfolio exposure, and macro filters.
4. Signal formula: raw score, normalized score, confidence, risk score, regime filter, and invalidation.
5. Execution assumptions: bar-close availability, conservative execution price, fee/slippage/liquidity cap, and max position size.
6. Validation: train/validation/out-of-sample split, parameter sweep, turnover, drawdown, tail risk, exposure time, and failure modes.
7. Output constraints: research-only language unless readiness, confidence, freshness, and risk gates pass.

## Research Workflow

1. Define a falsifiable thesis.
2. Build a `SignalSpec`.
3. Map required data sources and freshness requirements.
4. Run bias checks before measuring performance.
5. Run conservative backtests with fees, slippage, liquidity caps, and timestamp alignment.
6. Stress the signal across regimes and parameter grids.
7. Assign readiness: MVP Ready, Research-only, Enterprise-only, or Do not launch.
8. Publish only with disclaimers, confidence limits, and invalidation.

## Minimum Launch Criteria

MVP Ready strategies may appear in reports and signal surfaces with disclaimers when:

- Inputs are timestamped and fresh.
- The signal is not KOL sentiment alone.
- Confidence is capped when data is missing.
- Risk score is visible before expected payoff.
- Mock backtests are clearly labeled mock/research.
- No live trading path is enabled.

Research-only strategies can appear as observations but cannot produce high-confidence, actionable language. Enterprise-only strategies require licensed data, venue controls, or portfolio-specific risk limits. Do not launch strategies should remain internal until data and legal risks are resolved.
