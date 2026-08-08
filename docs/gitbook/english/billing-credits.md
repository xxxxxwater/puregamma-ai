# Billing & Credits
## Plans
| Plan | For | Highlights |
| --- | --- | --- |
| Free | Trial | Core markets & reports, starter credits |
| Silver | Individuals | More credits, full skill library |
| Max | Heavy users | High credit quota, iMessage Agent, wider data scopes |
| Enterprise | Teams | Custom quota and support |
Exact monthly credits, Agent run limits and data scopes are always shown live on the Billing page (the server is the single source of truth).
## How credits are charged
| Action | Metering |
| --- | --- |
| Daily brief (manual) | Fixed task rate; same-day regeneration hits cache |
| Event report | Fixed task rate; failures auto-refund in full |
| Agent run | Actual usage; cancellation settles partial |
| Secretary voice | 2–8 credits per message by length |
| Backtest run | Fixed task rate |
Billing uses **reserve → settle → refund**: an estimated amount is frozen first, then settled to actuals; failures refund automatically. Full history is visible on the Billing page.
## Managing your subscription
- The Billing page shows plan, balance and next refill.
- "Manage subscription" opens the Stripe customer portal (upgrade/downgrade/cancel/payment methods).
- Status syncs via Stripe webhooks; a few seconds of lag is normal.
## FAQ
- **402 error**: out of credits — upgrade or wait for the monthly refill.
- **Charged for a failed task?** Failed tasks auto-refund; check the ledger on the Billing page and contact support with a screenshot if anything looks off after 10 minutes.
