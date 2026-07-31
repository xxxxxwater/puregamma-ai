# NautilusTrader Runtime Integration

PureGamma uses NautilusTrader as an independently deployed strategy runtime. The API remains the authenticated control plane; the runtime never receives browser credentials and is not exposed as a public trading API.

## Architecture

```text
Agent / Strategy UI
        |
PureGamma API (auth, tenant isolation, credits, confirmation, audit)
        |
Trading Control Service (signed internal command + idempotency key)
        |
Nautilus Runtime :8090 (native MessageBus bridge, state, risk, recovery)
        |
Mock Exchange (PAPER/SHADOW only)
```

No NautilusTrader source is copied into this repository. The inspected local checkout is `1.231.0` at commit `321b534122`; because that version has no published wheel, the runtime image pins the latest installable compatible wheel, `nautilus_trader==1.230.0`. Upgrades require the runtime compatibility tests to pass first.

The runtime image uses Python 3.12 on Debian Bookworm and requires a binary Nautilus wheel. Source builds are intentionally disabled. Current Nautilus releases do not publish Intel macOS wheels, so Intel Mac development reports `nautilus.available=false`; use the Linux Docker runtime for native validation on that host.

## Implemented Modes

| Mode | Status | Notes |
| --- | --- | --- |
| BACKTEST | Enabled | Existing mock engine remains available; `engine=nautilus` uses native code when installed and otherwise reports simulation mode. |
| PAPER | Enabled | Persistent Mock Exchange runtime. |
| SHADOW | Enabled | Signals and state run without live order routing. |
| LIVE | Disabled | API, policy layer, runtime, adapters and account permissions deny it. |

Hyperliquid and Coinbase Advanced adapters currently expose configuration and health status only. Their order methods fail closed. Credentials do not activate live execution.

## Safety Defaults

```dotenv
NAUTILUS_LIVE_TRADING_ENABLED=false
NAUTILUS_ALLOW_LIVE_ORDER=false
NAUTILUS_EXECUTION_MODE=paper
NAUTILUS_ALLOW_WITHDRAWAL=false
NAUTILUS_ALLOW_TRANSFER=false
```

If any live flag is enabled, the PureGamma policy rejects all execution modes until the deployment is returned to the supported safe configuration. Withdrawal and transfer operations do not exist.

## Explicit Confirmation

Activation is two separate requests:

1. `POST /strategies/{id}/preview-activation` creates a short-lived intent against an immutable strategy version and returns an exact phrase.
2. `POST /strategies/{id}/activate` accepts that intent only when the user sends the exact phrase in a later request.

`好的`, `继续`, stale confirmations, modified strategy versions, expired intents and cross-user intents are rejected. The Agent may create and preview a strategy but cannot directly call an exchange.

Manual simulated orders use the same preview/confirm boundary. This feature remains a research simulator and is not an automated trading facility.

## Runtime State and Recovery

- Commands and order journal events are persisted in runtime SQLite.
- Command and client order IDs are idempotent.
- Orders uncertain during restart become `RECONCILIATION_REQUIRED`.
- Mismatched local and exchange state pauses new opening orders.
- Scheduled run sync executes every 60 seconds.
- Scheduled account reconciliation executes every five minutes.
- Operational safety reconciliation is not skipped because of user credit balance.

See [Runtime Operations](../trading/RUNTIME_OPERATIONS.md) and [Trading Safety](../trading/TRADING_SAFETY.md).

Phase 2 public-market PAPER/SHADOW behavior is documented in
[Phase 2 Public Market Runtime](../trading/PHASE_2_PUBLIC_MARKET_RUNTIME.md).

## Local Run

```bash
docker compose up --build nautilus-runtime api
cd apps/web
npm run dev
```

Health endpoints:

```text
GET http://localhost:8090/health
GET http://localhost:8000/trading/runtime/health
```

Only `/health` is public on the runtime. Runtime commands require `X-PG-Runtime-Secret`. In production, do not publish port 8090 outside the private service network.

## Backtest API Compatibility

The existing endpoint is preserved:

```json
POST /backtest
{
  "engine": "mock",
  "strategy_id": "optional-strategy-id",
  "strategy_name": "BTC momentum breakout",
  "asset": "BTC",
  "params": {"lookback_days": 30}
}
```

Set `engine` to `nautilus` to request the native engine path. The response always identifies the actual engine and mode used; fallback results are never labeled as native.

Backtests and simulated results are hypothetical. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
