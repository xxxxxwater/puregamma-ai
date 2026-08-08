# Portfolio NAV and Autopilot Production Review
Date: 2026-07-11
## Scope
- Plaid Investments account connection
- Interactive Brokers portfolio connection
- Hyperliquid public account connection
- Multi-account NAV and history
- Mobile interactive NAV chart
- Portfolio Research Autopilot
## Remediated launch blockers
1. Multi-account history previously summed only snapshots sharing the same minute. It now maintains the latest value for every active account at each event and emits total portfolio NAV.
2. Hyperliquid previously covered perpetual margin only. Spot balances are now valued with the public midpoint feed and included in NAV.
3. IBKR previously read only the first account. All returned portfolio accounts are now aggregated.
4. IBKR OAuth tokens now support encrypted refresh-token storage and expiry handling.
5. Plaid OAuth institutions can resume Link after redirect using a session-scoped Link token and `receivedRedirectUri`.
6. Sync failures are persisted on the connection and shown to the user instead of leaving a healthy status.
7. Users can disconnect an account. Encrypted credentials are removed immediately and the account leaves current NAV.
8. NAV freshness is explicit: Plaid uses a 36-hour window; IBKR and Hyperliquid use a 15-minute window.
9. Chart history is capped and downsampled to 500 points for browser performance.
10. Autopilot now creates persisted review records with NAV, concentration, freshness findings, data timestamp, and status.
11. Autopilot cadence is enforced by the scheduler. Telegram/iMessage delivery uses the notification dispatcher.
12. Long Gamma Watch calls the existing Deribit research engine and degrades explicitly when data is unavailable.
## Current implementation status
| Component | Code status | External requirement |
| --- | --- | --- |
| Hyperliquid | Ready for public API UAT | Public wallet address |
| Plaid Investments | Sandbox-ready | Plaid Investments product approval, client ID, secret, registered redirect URI |
| Interactive Brokers | OAuth adapter ready | IBKR Web API application, OAuth URLs/client credentials, approved redirect URI |
| NAV aggregation | Ready | At least one successful account sync |
| NAV chart | Ready | At least two portfolio snapshots |
| Autopilot sync/review | Ready | Worker and scheduler running |
| Telegram/iMessage delivery | Conditional | Provider credentials and plan entitlement |
## Required production configuration
Generate a Fernet key once and store it only in the production secret manager:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Required variables:
```env
PORTFOLIO_TOKEN_ENCRYPTION_KEY=
PLAID_ENV=production
PLAID_CLIENT_ID=
PLAID_SECRET=
PLAID_REDIRECT_URI=https://puregamma.ai/portfolio
IBKR_API_URL=https://api.ibkr.com/v1/api
IBKR_OAUTH_AUTHORIZE_URL=
IBKR_OAUTH_TOKEN_URL=
IBKR_CLIENT_ID=
IBKR_CLIENT_SECRET=
IBKR_REDIRECT_URI=https://puregamma.ai/portfolio
HYPERLIQUID_API_URL=https://api.hyperliquid.xyz
```
## UAT gates before public launch
1. Complete Plaid Sandbox Link, OAuth redirect, holdings sync, reconnect, and disconnect tests.
2. Complete IBKR OAuth authorization, refresh-token rotation, multi-account summary, paginated positions, reconnect, and disconnect tests using an approved IBKR application.
3. Verify Hyperliquid perpetual plus Spot valuation against the Hyperliquid UI for at least three wallets.
4. Run the scheduler for 48 hours and verify snapshot cadence, stale transitions, review cadence, and notification idempotency.
5. Validate PostgreSQL migrations `0006`, `0007`, and `0008` on a production-schema clone.
6. Confirm Plaid and IBKR data retention, display, and end-user consent language with the applicable vendor agreements.
## Known external launch gaps
- Plaid production access and Investments approval cannot be completed in code.
- IBKR OAuth endpoint details and scopes must match the approved IBKR application profile; generic placeholders are intentionally not treated as configured.
- Plaid webhook verification and event-driven refresh should be added before scaling beyond scheduled polling.
The application must continue to show `NEEDS CONFIG` until the relevant server-side credentials are present. No account connector is allowed to fall back to mock balances or positions.
