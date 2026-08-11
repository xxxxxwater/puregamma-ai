# Trading Safety Contract
PureGamma's current trading runtime is a research simulator. It supports backtests, PAPER and SHADOW modes. It does not support custody, withdrawals, transfers or live order execution.
## Invariants
- LIVE is denied in the API policy, runtime endpoint, adapter and account permission layers.
- **PAPER never submits to any real venue** — PAPER orders are rejected unless the venue is MOCK; only SHADOW may exercise a real (testnet) adapter.
- **Binance testnet submission is OFF by default** (`NAUTILUS_TESTNET_SUBMIT_ENABLED=true` required to enable, SHADOW mode only).
- Strategy versions are immutable once an activation preview is created.
- Any strategy modification invalidates prior confirmations.
- Confirmation is exact, short-lived, user-scoped and intent-scoped.
- All commands and journal entries carry idempotency keys.
- Risk checks execute before submission.
- Unknown order state pauses opening and requires reconciliation.
- Agent tools cannot bypass the control service.
## Risk Checks
The runtime checks max position, notional, leverage, daily loss, drawdown, stale account state, rate limits, reduce-only policy, account opening pause, the global kill switch, **aggregate (account-level) notional** and **exposure vs available margin** (fails closed when margin is unavailable and exposure is material).
## Reconciliation
- Local orders missing remotely (`unknown_open_orders`) pause opening.
- **Remote-only orders** (present on the exchange, never seen locally) are flagged and pause opening.
- Fills are compared on **count and notional**; divergence pauses opening.
## Execution Backend
`NAUTILUS_ENGINE_BACKEND=legacy` (default) selects the current pure-Python runtime; `nautilus` selects the NautilusTrader engine once Phase 1 lands. `legacy` remains the rollback path.
## Unsupported Operations
There are no endpoints for withdrawal, transfer, seed phrase, private key, custody or automatic live trading. Exchange adapter credentials are server-side only and cannot enable LIVE mode in this release.
Backtest and paper results are hypothetical. 
