# Exchange Read-only Keys

PureGamma AI exchange integrations must use read-only API keys only. Never enable withdrawal permissions, trading permissions, margin transfer, or account modification permissions.

Current status: backend account sync is planned. This document defines the security contract for Binance, OKX, Bybit, and Hyperliquid.

Portfolio and trade history are used for research context only. This is not financial advice or an official exchange statement.

## 1. Only Read-only Keys

Users must create API keys with read-only scopes. The UI and docs should reject or warn on any permission that allows:

- Withdrawals.
- Trading.
- Transfers.
- API key management.
- Sub-account administration.

## 2. Never Enable Withdrawal Permissions

Withdrawal-enabled keys are prohibited. If a provider API exposes permission introspection, PureGamma should reject unsafe keys automatically.

## 3. No Private Keys

Do not collect wallet private keys for exchange integrations.

## 4. No Seed Phrases

PureGamma must never request or store seed phrases.

## 5. Supported Exchanges

Target support:

- Binance.
- OKX.
- Bybit.
- Hyperliquid.

Current code has a placeholder `BinanceProvider` for public market data, not account sync.

## 6. Balance Sync

Planned flow:

1. User submits read-only exchange key.
2. API validates permissions if supported.
3. API encrypts key material.
4. Worker syncs spot, funding, and relevant account balances.
5. System normalizes balances into portfolio positions.
6. NAV marks source freshness and partial-data state.

## 7. Trade Sync

Trades should be synced for:

- Cost basis estimation.
- Position activity.
- Research context.
- Reconciliation against holdings.

Trades must not trigger order placement.

## 8. Key Encryption

Use:

```text
EXCHANGE_KEY_ENCRYPTION_KEY=...
```

Requirements:

- Encrypt API secrets and passphrases before persistence.
- Avoid logging full key IDs or secrets.
- Store permission metadata and last validation time.
- Rotate encryption keys with a migration plan.

## 9. Disconnect

Disconnect should:

- Delete encrypted key material.
- Stop sync jobs.
- Mark source as disconnected.
- Preserve historical normalized data only according to retention policy.
- Recalculate NAV with `partial_data=true` if the source was part of active NAV.

## 10. Troubleshooting

Common issues:

- Key has trading or withdrawal permissions: create a new read-only key.
- IP allowlist rejects PureGamma worker: add the correct outbound IP.
- Timestamp/signature mismatch: check server time.
- Exchange rate limit: reduce sync frequency.
- Missing balances: verify account type and sub-account selection.

See [Portfolio NAV Troubleshooting](../troubleshooting/PORTFOLIO_NAV.md).
