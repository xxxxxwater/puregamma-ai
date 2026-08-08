# Plaid
Plaid is used for investments data only. PureGamma AI does not use Plaid for trading, money movement, order placement, custody, or account control.
Current status: Plaid backend routes and persistence are planned. The frontend integration page uses fallback data. This document defines the intended secure contract.
Portfolio output is an estimate and not financial, tax, or official broker advice.
## 1. Investments Data Only
Use Plaid for:
- Holdings.
- Securities.
- Investment transactions.
- Account metadata needed for portfolio research.
Do not use Plaid for:
- Trading.
- Transfers.
- Payment initiation.
- Credential storage outside Plaid Link.
## 2. Sandbox Mode
Local settings:
```text
PLAID_ENV=sandbox
PLAID_CLIENT_ID=...
PLAID_SECRET=...
PLAID_PRODUCTS=investments
```
Use sandbox for local development and test fixtures.
## 3. Create Link Token
Planned endpoint:
```text
POST /integrations/plaid/link-token
```
Expected behavior:
- Requires bearer auth.
- Creates a Plaid Link token for `investments`.
- Stores no access token at this step.
- Returns `link_token`.
## 4. Exchange Public Token
Planned endpoint:
```text
POST /integrations/plaid/exchange-public-token
```
Request:
```json
{"public_token":"public-sandbox-..."}
```
Expected behavior:
- Exchanges `public_token` for `access_token`.
- Encrypts access token before persistence.
- Stores item ID and account metadata.
- Never returns access token to the browser.
## 5. Encrypted Access Token
Plaid access tokens must be encrypted with a key such as:
```text
PORTFOLIO_TOKEN_ENCRYPTION_KEY=...
```
Security requirements:
- Do not log access tokens.
- Rotate encryption keys with a migration plan.
- Delete token on disconnect.
- Scope database reads by user or tenant.
## 6. Sync Holdings
Planned sync:
```text
POST /integrations/plaid/sync
```
Expected fields:
- Account ID.
- Security ID.
- Quantity.
- Institution value when available.
- Timestamp.
## 7. Sync Securities
Securities normalize instrument metadata:
- Ticker.
- Name.
- Type.
- Currency.
- Proxy mapping, for example MSTR as equity proxy.
## 8. Sync Investment Transactions
Transactions support:
- Cost basis estimation.
- Realized activity history.
- Deposit/withdrawal awareness.
- Audit trail for NAV changes.
Do not infer tax lots unless the data is complete and the product explicitly supports it.
## 9. Disconnect
Planned endpoint:
```text
DELETE /integrations/plaid/items/{item_id}
```
Expected behavior:
- Remove encrypted access token.
- Stop future sync.
- Keep or delete historical normalized data based on user request and retention policy.
- Mark affected NAV as partial if other sources remain.
## 10. Data Privacy
Plaid data can reveal brokerage holdings and wealth profile. Treat it as restricted user data:
- Encrypt tokens.
- Minimize raw Plaid payload retention.
- Store normalized holdings separately from secrets.
- Log only safe identifiers.
- Honor deletion requests.
## 11. Troubleshooting
See [Plaid Sync Troubleshooting](../troubleshooting/PLAID_SYNC.md).
Common issues:
- Sandbox credentials missing.
- Link token expired.
- Public token already exchanged.
- Investment account unsupported.
- Holdings stale.
- Item requires user re-authentication.
