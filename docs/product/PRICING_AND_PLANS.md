# Pricing and Plans

PureGamma AI uses a subscription plus credits model. Subscriptions control entitlements, and credits meter high-cost research actions.

Pricing and credits are product configuration, not investment performance claims. PureGamma AI does not promise returns.

## Plans

Plans are defined in `packages/billing/plans.py`.

| Plan | Monthly price | Monthly credits | Reports | Alerts | Data sources | Channels | High-cost tasks |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| Free | $0 | 30 | 1/day | 0 | mock, delayed market | email | No |
| Pro | $29.90 | 1000 | 1/day | 20 | market, RSS, basic backtest | Telegram, email | Yes |
| Max | $199 | 10000 | 5/day | 500 | market, RSS, X, on-chain, Coinglass, Glassnode, advanced backtest | Telegram, Slack, email, iMessage | Yes |
| Enterprise | Custom | 50000 default | 100/day | 10000 | all, API, custom, private deployment | Telegram, Slack, email, iMessage | Yes |

## Credit Costs

Credit costs are defined in `packages/billing/credits.py`.

| Action | Credits |
| --- | ---: |
| Daily market report | 10 |
| Event report | 5 |
| Sentiment scan | 8 |
| X sentiment scan | 20 |
| On-chain scan | 12 |
| Backtest | 25 |
| Playbook generation | 30 |
| Telegram alert | 1 |
| Slack alert | 1 |
| Email alert | 1 |
| iMessage alert | 3 |

## Entitlement Behavior

- Past-due subscriptions restrict high-cost tasks.
- iMessage requires a plan that includes the `imessage` channel and a non-past-due subscription.
- Notification sends are skipped when the channel is not entitled, the recipient is missing, or the user has insufficient credits.
- Failed provider sends refund the consumed notification credits.

## Billing Mode

`BILLING_MODE=mock` is for local demos and does not call Stripe.

`BILLING_MODE=stripe` enables real Stripe Checkout, Customer Portal, signature-verified webhooks, subscription updates, and monthly credit grants.

See [Stripe](../integrations/STRIPE.md) and [Credit and Entitlements](../developer/CREDIT_AND_ENTITLEMENTS.md).
