# Pricing and Plans
PureGamma AI uses a subscription plus credits model. Subscriptions control entitlements, and credits meter high-cost research actions.
Pricing and credits are product configuration, not investment performance claims. PureGamma AI does not promise returns.
> **Single source of truth:** `packages/billing/plans.py` and `packages/billing/credits.py`. This document mirrors them; if numbers diverge, the code wins and this file must be updated.
## Plans
Plans are defined in `packages/billing/plans.py`.
| Plan | Monthly price | Monthly credits | Agent runs/day | Concurrent | Reports/day | Alerts/month | Portfolios | Data sources | Channels | High-cost tasks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| Free | $0 | 150 | 5 | 1 | 1 | 10 | 1 | market, RSS, portfolio | email, push | No |
| Invite Preview | $0 | 300 | 20 | 1 | 1 | 50 | 1 | market, RSS, fintwit, portfolio | telegram, email, push | Yes |
| Pro | $29.90 | 3000 | 50 | 2 | 1 | 100 | 1 | market, RSS, fintwit, portfolio, options | telegram, email, push | Yes |
| Max | $199 | 15000 | 200 | 4 | 5 | 1000 | 5 | market, RSS, fintwit, portfolio, options, X, on-chain, Coinglass, Glassnode | telegram, slack, email, iMessage, push | Yes |
| Enterprise | Custom | 50000 | 1000 | 10 | 100 | 10000 | 100 | all | telegram, slack, email, iMessage, push | Yes |
Note: `backtest_tier` is `none` for Free/Pro, `basic` for Invite Preview, `advanced` for Max/Enterprise (see `plans.py`).
## Credit Costs
Credit costs are defined in `packages/billing/credits.py`.
| Action | Credits |
| --- | ---: |
| Daily market report | 4 |
| Event report | 5 |
| Sentiment scan | 8 |
| X sentiment scan | 20 |
| On-chain scan | 12 |
| Backtest | 50 |
| Backtest export | 50 |
| Playbook generation | 30 |
| Portfolio daily brief | 8 |
| Daily combined iMessage | 15 |
| DeepSeek report generation | 10 |
| DeepSeek playbook generation | 30 |
| Telegram alert | 1 |
| Slack alert | 1 |
| Email alert | 1 |
| iMessage alert | 2 |
| Push alert | 1 |
| Strategy generation | 5 |
| Strategy modification | 2 |
| Strategy activation | 5 |
| Runtime reconciliation | 2 |
| Manual order preview | 1 |
| Agent chat / research (basic, market, news, portfolio, advanced data) | 2 |
| Agent deep research | 10 |
| Agent Luna research | 6 |
| Private secretary reply | 20 |
| Research run | 20 |
## Entitlement Behavior
- Past-due or incomplete subscriptions restrict high-cost tasks (effective plan falls back to Free).
- iMessage requires a plan that includes the `imessage` channel and a non-restricted subscription.
- Notification sends are skipped when the channel is not entitled, the recipient is missing, or the user has insufficient credits.
- Failed provider sends refund the consumed notification credits; mock recipients are never billed.
- Strategy activation and runtime reconciliation are metered high-cost actions (see `credits.py`).
## Billing Mode
`BILLING_MODE=mock` is for local demos only; the API rejects mock upgrades when the environment is production or billing is wired to Stripe.
`BILLING_MODE=stripe` (required in production) enables real Stripe Checkout, Customer Portal, signature-verified webhooks, subscription updates, and monthly credit grants.
See [Stripe](../integrations/STRIPE.md) and [Credit and Entitlements](../developer/CREDIT_AND_ENTITLEMENTS.md).
