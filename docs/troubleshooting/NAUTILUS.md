# Nautilus Troubleshooting

Current backend backtests use a mock engine. Real NautilusTrader runtime integration is planned.

Backtests are hypothetical and not financial advice.

## `402` on `/backtest`

Cause:

- Insufficient credits.
- High-cost task entitlement denied.
- Subscription is past due.

Fix:

```bash
curl -X POST http://localhost:8000/billing/mock-upgrade \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan_name":"Max"}'
```

## Backtest Not Found

Cause:

- Wrong run ID.
- Run belongs to a different user.

Fix: list or store the run ID from `POST /backtest`.

## Metrics Look Unrealistic

Current engine uses generated returns. Treat metrics as UI/test data only.

For production:

- Validate data source.
- Add fees and slippage.
- Add liquidity constraints.
- Add benchmark.
- Check lookahead bias.

## Live Trading Flag Enabled

MVP should keep:

```text
NAUTILUS_LIVE_TRADING_ENABLED=false
NAUTILUS_ALLOW_LIVE_ORDER=false
```

If either is true in MVP, disable immediately and audit deployment history.
