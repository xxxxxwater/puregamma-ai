# Portfolio NAV

Portfolio NAV is the estimated net asset value of synced brokerage, exchange, and on-chain positions. It is designed for research context, not accounting, tax filing, custody reconciliation, or official statements.

Required disclaimer: Portfolio NAV is an estimate. It is not tax advice, not financial advice, and not an official broker, custodian, or exchange statement.

## Current Status

The web app includes a Portfolio page with fallback data. Backend tables, sync jobs, and API routes for portfolio accounts, positions, transactions, prices, and NAV snapshots are not implemented yet.

## What NAV Means

NAV means:

```text
sum(position_quantity * selected_price) + cash + stablecoins - known liabilities
```

For the MVP, liabilities are not modeled. If liabilities are introduced later, they must be explicit and source-attributed.

## Data Sources

Planned sources:

- Plaid investments data for brokerage holdings, securities, and investment transactions.
- Exchange read-only keys for balances and historical trades.
- On-chain wallet addresses for public token balances and stablecoins.
- Market data providers for current prices.
- Manual fallback entries for unsupported instruments, if explicitly marked.

## Calculation Method

1. Normalize all positions into canonical assets.
2. Convert quantities into a shared base currency, normally USD.
3. Select the best available price source by asset and timestamp.
4. Mark stale or missing prices.
5. Aggregate values by account, asset, asset class, and source.
6. Calculate allocation weights.
7. Estimate daily PnL when prior quantity and price data are available.
8. Attach source freshness metadata to every snapshot.

## Pricing Sources

Priority should be:

1. Exchange or broker-provided official position price when available.
2. Trusted market data provider for liquid assets.
3. Stablecoin peg logic for supported stablecoins.
4. Last known price with a stale-data warning.
5. Manual value only when source and timestamp are explicit.

## Partial Data

NAV must show `partial_data=true` when:

- One or more linked accounts failed to sync.
- A wallet chain or RPC endpoint is unavailable.
- A position has no reliable price.
- Plaid data is delayed.
- Exchange keys were disconnected.

Do not hide partial-data state in user-facing views.

## Stale Data

Each account, position, and price should carry `last_synced_at` and `price_timestamp`. Stale thresholds should be configurable by source:

- Exchange balances: 15 minutes.
- On-chain wallets: 30 minutes.
- Plaid investments: 24 hours.
- Manual entries: always marked manual.

## Stablecoins

Stablecoins should default to $1 only when the token is supported, liquid, and no depeg warning is active. If a stablecoin trades materially below or above peg, use market price and show a warning.

## Unrealized PnL

Unrealized PnL requires cost basis. Cost basis may be unavailable or inconsistent across Plaid, exchanges, and on-chain transfers. When cost basis is missing, show position value without PnL rather than guessing.

## Allocation and Risk Metrics

Portfolio views should show:

- Asset allocation.
- Source allocation.
- Crypto vs equity vs stablecoin/cash.
- Concentration risk.
- BTC beta estimate.
- Drawdown or stress estimate when inputs are available.

Risk metrics are research estimates, not guarantees.

## Troubleshooting Incorrect NAV

See [Portfolio NAV Troubleshooting](../troubleshooting/PORTFOLIO_NAV.md).
