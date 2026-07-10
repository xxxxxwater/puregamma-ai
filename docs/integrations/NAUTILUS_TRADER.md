# NautilusTrader

NautilusTrader is planned as PureGamma.ai's research, backtest, and paper-trading analysis layer. Live trading is disabled by default.

Backtests are hypothetical and do not guarantee future results. PureGamma.ai does not place live trades in the current product.

## 1. Role in PureGamma

NautilusTrader is intended to support:

- Research-grade strategy testing.
- Event replay.
- Paper trading research.
- Metrics and drawdown analysis.
- Strategy comparison.

Current code has `packages/backtest/BacktestEngine`, which is a mock/simulated engine, not a full NautilusTrader runtime.

## 2. Research, Backtest, Paper Trading Only

Allowed:

- Backtests.
- Paper trading simulations.
- Strategy diagnostics.
- Risk analysis.

Not allowed in MVP:

- Live order routing.
- Custody.
- Exchange account trading.
- Automated execution.

## 3. Live Trading Disabled by Default

Required safety flags:

```text
NAUTILUS_LIVE_TRADING_ENABLED=false
NAUTILUS_ALLOW_LIVE_ORDER=false
```

Do not change these for MVP deployments.

## 4. Mock Mode

Frontend Nautilus page uses fallback data. Backend `/backtest` uses the internal mock engine and costs 25 credits.

```bash
curl -X POST http://localhost:8000/backtest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"strategy_name":"BTC momentum breakout","asset":"BTC","params":{"lookback_days":30}}'
```

## 5. Strategy List

Current strategy/playbook list:

- BTC momentum breakout.
- ETH/BTC rotation.
- SOL high beta rotation.
- HYPE trend following.
- MSTR premium / BTC proxy trade.
- STRC event-driven credit trade.

## 6. Running Backtests

Endpoint:

```text
POST /backtest
```

Request:

```json
{
  "strategy_name": "BTC momentum breakout",
  "asset": "BTC",
  "params": {"lookback_days": 30}
}
```

Requirements:

- Bearer auth.
- High-cost task entitlement.
- 25 credits.

## 7. Metrics

Current mock metrics:

- Total return.
- Sharpe.
- Max drawdown.
- Win rate.

Future Nautilus integration should add:

- Exposure.
- Turnover.
- Slippage.
- Fees.
- Latency assumptions.
- Benchmark comparison.
- Regime segmentation.

## 8. Risk Assumptions

Every backtest must state:

- Data source.
- Time period.
- Fees.
- Slippage.
- Liquidity assumptions.
- Position sizing.
- Rebalancing rules.
- Whether survivorship or lookahead bias may exist.

## 9. Why Backtests Are Not Guarantees

Backtests depend on historical data, assumptions, and simplifications. They can overfit, omit liquidity constraints, and fail in future regimes.

Use disclosure from [Backtest Disclosure](../compliance/BACKTEST_DISCLOSURE.md).

## 10. Troubleshooting

See [Nautilus Troubleshooting](../troubleshooting/NAUTILUS.md).

Common issues:

- `402` response: insufficient credits or entitlement denied.
- Unknown strategy: register the strategy.
- Unrealistic metrics: inspect assumptions and mock data.
- Live trading flag enabled: disable immediately in MVP.
