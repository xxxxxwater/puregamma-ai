# Credit and Entitlements
Credits meter high-cost research and notification actions. Entitlements control plan access to data sources, channels, and high-cost tasks.
Credits are product usage controls, not investment-performance indicators.
## Plans
Defined in `packages/billing/plans.py`.
| Plan | Monthly credits | Channels | High-cost tasks |
| --- | ---: | --- | --- |
| Free | 30 | email | No |
| Pro | 1000 | telegram, email | Yes |
| Max | 10000 | telegram, slack, email, imessage | Yes |
| Enterprise | 50000 default | telegram, slack, email, imessage | Yes |
## Costs
Defined in `packages/billing/credits.py`.
| Action | Cost |
| --- | ---: |
| `daily_market_report` | 10 |
| `event_report` | 5 |
| `sentiment_scan` | 8 |
| `x_sentiment_scan` | 20 |
| `onchain_scan` | 12 |
| `backtest` | 50 |
| `playbook_generation` | 30 |
| `telegram_alert` | 1 |
| `slack_alert` | 1 |
| `email_alert` | 1 |
| `imessage_alert` | 3 |
## Credit Ledger
Credit changes write `credit_ledger` with:
- `action`
- `credits_delta`
- `balance_after`
- `metadata`
- `created_at`
Consumption uses row locking through `with_for_update`.
## Entitlement Checks
`packages/billing/entitlements.py` computes:
- Monthly credits.
- Max daily reports.
- Max alerts.
- Allowed data sources.
- Notification channels.
- High-cost task access.
- iMessage access.
- Payment failure restriction reason.
Past-due subscriptions block high-cost tasks and iMessage.
## Notification Credits
Notification flow:
1. Check idempotency.
2. Check recipient.
3. Check entitlement.
4. Check iMessage length/rate limit if relevant.
5. Consume credits.
6. Send provider request.
7. Refund credits if provider fails.
## Stripe Grants
Monthly credits are granted by:
- Mock upgrade.
- Checkout completion.
- `invoice.paid` for subscription cycles.
Duplicate webhook events must not double-grant credits.
