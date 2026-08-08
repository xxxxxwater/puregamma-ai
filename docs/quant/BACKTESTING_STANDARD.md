# Backtesting Standard
PureGamma backtests must satisfy the following controls before being used in product research.
## Mandatory Controls
1. Data must not contain future information.
2. Signals become available only after bar close.
3. Funding and OI require timestamp alignment.
4. News and KOL events require publication timestamps.
5. Execution prices must be conservative.
6. Fees must be included.
7. Slippage must be included.
8. Liquidity caps must be included.
9. Max position size must be included.
10. Borrow and funding assumptions must be included when relevant.
11. Train, validation, and out-of-sample periods must be separated.
12. Reports must not show only the best parameter set.
13. Drawdown and tail risk must be output.
14. Trade count and turnover must be output.
15. Exposure time must be output.
## Required Metrics
- Total return
- Sharpe or another risk-adjusted return
- Max drawdown
- Tail loss / downside percentile
- Win rate
- Trade count
- Turnover
- Exposure time
- Fee and slippage paid
- Capacity and liquidity utilization
## Bias Checks
Look-ahead bias: reject a run if any feature timestamp is later than the simulated decision time.
Survivorship bias: universes must be point-in-time where possible. Newer assets such as HYPE must include delisting, venue, and missing-history disclaimers.
Parameter overfitting: parameter choices must be stable across nearby values and out-of-sample periods. If the edge exists only at one narrow setting, readiness is capped at Research-only.
