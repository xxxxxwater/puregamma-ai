# Strategy Validation Checklist
Use this checklist before moving any strategy beyond research draft status.
## Data
- Required data sources exist.
- Data source license allows product use.
- Timestamps are point-in-time.
- Freshness requirements are defined.
- Missing data lowers confidence.
## Signal
- Signal formula is explicit.
- Entry, exit, and invalidation are explicit.
- KOL sentiment is not the only trigger.
- Regime filter can mark the strategy inactive.
- Liquidity and leverage assumptions are defined.
## Backtest
- No look-ahead bias.
- Survivorship bias reviewed.
- Fees, slippage, funding, and borrow costs included.
- Position caps and liquidity caps included.
- Train/validation/out-of-sample split used.
- Parameter grid reported.
- Drawdown, tail risk, turnover, trade count, and exposure time reported.
## Product Output
- Readiness is assigned.
- Risk score appears before payoff language.
- Expected payoff is framed as scenario, not promise.
- Research-only strategies avoid actionable language.
- Mock backtests are labeled mock.
- Live trading remains disabled.
