# Phase 2: Public Market Paper Runtime

Phase 2 connects authenticated PAPER and SHADOW strategy runs to real public
market quotes. It does not enable live exchange execution.

## Data flow

```text
Hyperliquid allMids / Coinbase Exchange ticker
  -> isolated public market providers
  -> timeout, cache, failure isolation and circuit breaker
  -> runtime market_quotes store
  -> confirmed RUNNING strategy
  -> STRATEGY_SIGNAL event
  -> SHADOW: event only
  -> PAPER: risk check -> order journal -> Mock Exchange simulated fill
```

Hyperliquid uses the official `POST https://api.hyperliquid.xyz/info` endpoint
with `{"type":"allMids"}`. Coinbase uses the official public Exchange ticker
endpoint at `GET https://api.exchange.coinbase.com/products/{product_id}/ticker`.
Neither provider accepts credentials or sends signed actions.

## Safety boundaries

- A strategy must have completed the existing explicit activation confirmation.
- SHADOW cannot create an order.
- PAPER orders are sent only to `MockExchangeGateway` and are marked as simulated.
- Hyperliquid and Coinbase execution adapters remain fail-closed.
- LIVE, withdrawals, transfers, wallet signing and private-key intake remain absent.
- Public quotes are shared; strategy events are filtered by user-owned runtime run IDs.

## Runtime behavior

- Quotes normalize to asset, symbol, price, provider and UTC timestamp.
- The in-memory cache defaults to five seconds.
- Three consecutive provider failures open its circuit for sixty seconds.
- Hyperliquid is queried first; Coinbase fills missing supported assets.
- A 20-point per-run price history persists in runtime SQLite.
- Duplicate signal direction is suppressed until direction changes.
- PAPER signals use strategy and risk-policy limits before simulated fill.

## Configuration

```dotenv
NAUTILUS_PUBLIC_MARKET_DATA_ENABLED=true
NAUTILUS_MARKET_REFRESH_INTERVAL_SECONDS=15
NAUTILUS_HYPERLIQUID_PUBLIC_URL=https://api.hyperliquid.xyz
NAUTILUS_COINBASE_PUBLIC_URL=https://api.exchange.coinbase.com
NAUTILUS_MARKET_DATA_TIMEOUT_SECONDS=5
NAUTILUS_MARKET_DATA_CACHE_TTL_SECONDS=5
NAUTILUS_MARKET_DATA_FAILURE_THRESHOLD=3
NAUTILUS_MARKET_DATA_RECOVERY_SECONDS=60
```

## APIs

- `GET /trading/runtime/market`: cached shared quote state.
- `GET /trading/runtime/market?refresh=true`: manual public quote refresh.
- `GET /trading/runtime/events`: current user's runtime events only.

The internal runtime equivalents require `X-PG-Runtime-Secret`.

This is simulated research infrastructure. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
