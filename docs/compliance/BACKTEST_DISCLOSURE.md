# Backtest Disclosure
Backtests in PureGamma AI are hypothetical research outputs. They do not predict or guarantee future results.
## Required Disclosure
```text
Backtests are hypothetical, depend on assumptions, and do not guarantee future results. 
```
## Required Metadata
Every backtest should identify:
- Strategy name.
- Asset.
- Time period.
- Data source.
- Fees.
- Slippage.
- Position sizing.
- Rebalancing rules.
- Liquidity assumptions.
- Whether live trading is disabled.
## Current Implementation
The current backend uses a mock `BacktestEngine` with generated returns. It is not a full NautilusTrader runtime and should not be used for production investment decisions.
## Risk Factors
- Overfitting.
- Lookahead bias.
- Survivorship bias.
- Data quality issues.
- Missing fees or slippage.
- Liquidity constraints.
- Regime changes.
## UI Requirements
- Show disclaimer near metrics.
- Avoid ranking strategies only by total return.
- Show max drawdown and risk assumptions.
- Label mock or incomplete data clearly.
