# PureGamma Nautilus Runtime

The production image pins the latest published compatible binary wheel,
`nautilus_trader==1.230.0`, and refuses source builds. The separately cloned
`1.231.0` repository was used for API review only and is not copied or mounted
into this service.

Intel macOS is not supported by the current upstream wheel matrix. On that
platform the service runs Mock Exchange PAPER/SHADOW mode and reports the
native bridge as unavailable. Use the Linux Docker image for native validation.

This service is the isolated execution data plane. The PureGamma API remains the authenticated control plane. The runtime accepts only HMAC-secret-protected internal commands and supports BACKTEST, PAPER, SHADOW, and Mock Exchange in this phase.

It does not accept LIVE orders, withdrawals, transfers, wallet signing, or private keys. A local NautilusTrader checkout is an implementation reference; its source is not copied into PureGamma.

```bash
cd services/nautilus-runtime
python -m pip install -r requirements.txt
NAUTILUS_RUNTIME_SECRET=change-me PYTHONPATH=. uvicorn app.main:app --port 8090
```

## Execution mode matrix (P0-10a)

The exchange gateway is selected per account via the adapter registry
(`app/adapter_registry.py`) keyed on `(venue, environment)` from the account
record carried in the run config. Unknown venues fail closed with an explicit
`UnavailableAdapter` reason — never a silent mock fallback.

| Mode | Adapter selection | Market data | Order submission | Fills | Accounting / reconcile |
| --- | --- | --- | --- | --- | --- |
| BACKTEST | none (control plane) | historical | none | simulated by backtest engine | backtest metrics only |
| PAPER | `MOCK` → `MockExchangeGateway` | public router quotes | mock gateway only | immediate simulated fill at quote price | paper positions/PnL, journal + reconcile vs mock |
| SHADOW | real adapter wrapped by `ShadowExecutionAdapter` (e.g. Binance testnet book) | real adapter prices/order book | **never submitted** | simulated walk-the-book VWAP against adapter depth; rests if book is thin | full journal/positions/PnL + reconcile vs paper accounting |
| TESTNET (PAPER-mode run on a testnet account) | `BINANCE`+`testnet` → `BinanceSpotTestnetAdapter` (`https://testnet.binance.vision`) | adapter | real HMAC-signed spot orders, `newClientOrderId` = idempotency key | venue fills mapped to ack/reject states | journal + reconcile vs adapter balances/fills drift |
| LIVE | — | — | **disabled** (`UnavailableAdapter`, config-validated) | — | — |

Invariants enforced in every mode:

- `NAUTILUS_EXECUTION_MODE` must remain `paper` or `shadow`; live order,
  withdrawal and transfer flags are validated off in production config
  (API and runtime side).
- Withdrawals/transfers hard-fail on every adapter, including Binance testnet.
- The global kill switch blocks order submission on **all** adapters before
  any venue call; paused runs reject new opening intents (`RUN_PAUSED`) while
  reduce-only closes stay allowed; stop cancels resting orders first.
- Order intents are idempotent: `idempotency_key = "{strategy_id}:{signal_id}"`
  with a deterministic `client_order_id`, so duplicate signals/commands dedup.
- OrderJournal transitions are append-only and validated against
  `packages/trading/states/order_state.py`; uncertain orders are marked
  `RECONCILIATION_REQUIRED` on boot and re-synced from the adapter
  (`RuntimeManager.recover()`), failing closed (opening paused) when the
  adapter has no record.

Binance testnet credentials are read from `BINANCE_TESTNET_API_KEY` /
`BINANCE_TESTNET_API_SECRET` (see `.env.example`) and are never logged.
