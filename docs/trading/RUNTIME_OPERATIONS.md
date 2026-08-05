# Runtime Operations

## Services

- `api`: authentication, strategy versions, billing, confirmation and audit.
- `nautilus-runtime`: internal command processor, native Nautilus bridge, Mock Exchange and recovery state.
- `worker` / scheduler: status synchronization and reconciliation.

The runtime stores operational state in `NAUTILUS_RUNTIME_STATE_DB`. Mount this path on durable storage and back it up with the main database.

## Health Interpretation

- `status=HEALTHY`: the control process and Mock Exchange are available.
- `nautilus.available=true`: the pinned native wheel initialized successfully.
- `nautilus.available=false`: Mock PAPER/SHADOW can run, but native backtests are unavailable.
- `adapters[].status=NEEDS_CREDENTIALS`: status-only external adapter has no configuration.
- `adapters[].status=LIVE_DISABLED`: credentials exist, but live execution remains disabled.
- `recoveredOrders>0`: restart found uncertain order journal entries and marked them for reconciliation.

## Recovery Procedure

1. Keep the global kill switch enabled when state is uncertain.
2. Inspect `/trading/orders` and the latest `reconciliation_records` rows.
3. Call `POST /trading/reconcile` for the affected account.
4. Do not resume a strategy while status is `RECONCILIATION_REQUIRED`.
5. Resume only after local orders, exchange open orders and fills agree.

The first phase uses Mock Exchange only. External adapter reconciliation is intentionally unavailable.

## Secret Rotation

Rotate `NAUTILUS_RUNTIME_SECRET` in both API and runtime at the same deployment boundary. Never log it, expose it to the browser, or store it in strategy JSON.

## Alerts

Alert on runtime unavailability, repeated reconciliation errors, recovered uncertain orders, global kill switch changes, risk rejection spikes and any attempted LIVE command.
