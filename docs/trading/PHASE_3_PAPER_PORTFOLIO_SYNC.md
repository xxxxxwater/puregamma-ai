# Phase 3: Persistent Paper Portfolio Sync

Phase 3 persists PAPER execution state inside the isolated Nautilus runtime and
projects that state into the PureGamma application database. LIVE execution,
withdrawals, transfers, and wallet signing remain unavailable.

## Runtime ledger

- Orders, paper positions, market quotes, runs, commands, and events live in the
  runtime SQLite database configured by `NAUTILUS_RUNTIME_STATE_DB`.
- The Mock Exchange restores the latest order state and paper positions after a
  process restart.
- Public quotes mark open positions before strategy evaluation. Account equity,
  available margin, exposure, daily PnL, and drawdown derive from that ledger.
- `GET /accounts/{account_id}/state` is protected by the internal runtime secret.

## Main database projection

`sync_runtime_account` projects runtime state into the existing models:

- account state to `AccountSnapshot`
- positions to `PositionSnapshot`
- automatic PAPER decisions to `OrderIntent` and `OrderJournal`
- strategy events to `SignalEvent`, including provider URL and timestamps
- sync operations to `TradingAuditLog`

State snapshots use a deterministic content fingerprint. Orders use client order
ID plus sequence, and signals use the runtime event ID. Replaying a sync does not
duplicate records.

## Operation

- For direct local execution, start the runtime from the repository root with
  `uvicorn app.main:app --app-dir services/nautilus-runtime --port 8090`. This
  keeps both the runtime app and shared `packages` imports on the Python path.
- The scheduler invokes `puregamma.sync_nautilus_paper_accounts` at
  `NAUTILUS_RUNTIME_SYNC_INTERVAL_SECONDS`.
- An authenticated user can invoke `POST /trading/runtime/sync` only for an
  account they own.
- `GET /trading/positions` returns the latest snapshot per account/instrument.
- `GET /trading/performance` returns the latest account performance snapshot.
- Operational synchronization does not consume user credits.

If the runtime is unavailable, the worker rolls back that account's sync and
continues with other accounts. Existing snapshots remain readable and are not
replaced with fabricated data.

## Safety boundary

This phase uses Mock Exchange PAPER fills only. It does not submit exchange
orders or introduce exchange credentials. Runtime and API checks continue to
reject `LIVE` mode.
