# Trading Safety Contract

PureGamma's current trading runtime is a research simulator. It supports backtests, PAPER and SHADOW modes. It does not support custody, withdrawals, transfers or live order execution.

## Invariants

- LIVE is denied in the API policy, runtime endpoint, adapter and account permission layers.
- Strategy versions are immutable once an activation preview is created.
- Any strategy modification invalidates prior confirmations.
- Confirmation is exact, short-lived, user-scoped and intent-scoped.
- All commands and journal entries carry idempotency keys.
- Risk checks execute before submission.
- Unknown order state pauses opening and requires reconciliation.
- Agent tools cannot bypass the control service.

## Risk Checks

The phase-one runtime checks max position, notional, leverage, daily loss, drawdown, stale account state, rate limits, reduce-only policy, account opening pause and the global kill switch.

## Unsupported Operations

There are no endpoints for withdrawal, transfer, seed phrase, private key, custody or automatic live trading. Exchange adapter credentials are server-side only and cannot enable LIVE mode in this release.

Backtest and paper results are hypothetical. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
