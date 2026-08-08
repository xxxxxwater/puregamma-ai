# Billing Architecture
PureGamma AI supports two Stripe checkout entrypoints:
- Checkout Sessions for app-created subscription sessions.
- Payment Links for Stripe-hosted checkout URLs.
Both paths converge on signed Stripe webhooks and a local `BillingCheckoutIntent` record. The success URL is informational only and never upgrades a user.
## Core Tables
- `Subscription`: current Stripe subscription mirror.
- `CreditLedger`: credit grants, consumption, refunds, and idempotency metadata.
- `StripeWebhookEvent`: Stripe event idempotency, raw payload hash, manual review, and errors.
- `BillingCheckoutIntent`: local checkout intent linking user, plan, checkout mode, Stripe session/link, and review state.
## Checkout Session Flow
1. User clicks upgrade.
2. API creates `BillingCheckoutIntent(checkout_mode="session")`.
3. API creates Stripe Checkout Session with `mode=subscription`.
4. Session metadata includes `user_id`, `plan_name`, and `checkout_intent_id`.
5. `client_reference_id` is set to the public checkout intent reference.
6. `checkout.session.completed` verifies the subscription and updates subscription, plan, and credits.
## Payment Link Flow
1. User clicks upgrade while `BILLING_CHECKOUT_MODE=payment_link`.
2. API creates `BillingCheckoutIntent(checkout_mode="payment_link")`.
3. API returns a plan-specific Payment Link URL with `client_reference_id`.
4. Stripe webhook maps the checkout by `client_reference_id`, price ID, and metadata.
5. Unknown plan mapping enters manual review.
`STRIPE_PAYMENT_LINK_PRIMARY` is intentionally treated as ambiguous. A primary link completion requires a trusted price ID or explicit plan metadata before automatic upgrade.
## Manual Review
Events enter manual review when automatic mapping would require guessing:
- unknown price ID
- missing known user
- missing checkout intent
- primary Payment Link without plan proof
- subscription event with unknown price
Admin endpoints:
```text
GET /admin/stripe-events
GET /admin/billing-intents
POST /admin/billing-intents/{intent_id}/resolve
```
Manual resolve grants monthly credits once by `manual_resolve_intent_id` and records `resolved_by_admin_id` in intent metadata.
## Webhook Idempotency
`StripeWebhookEvent.stripe_event_id` prevents the same Stripe event from running twice. Credit grants add a second layer:
- checkout completion grants are keyed by `subscription_id`
- renewal grants are keyed by `invoice_id`
- manual grants are keyed by `manual_resolve_intent_id`
This prevents duplicate credits when Stripe retries, operators replay events, or two event IDs reference the same invoice.
## Operational Checks
```bash
curl http://localhost:8000/health
stripe listen --forward-to localhost:8000/stripe/webhook
stripe projects status --json
python3 -m pytest tests/test_billing.py tests/integration/test_stripe_webhook.py
```
Do not store Stripe secrets in code, docs, or `.projects/vault`.
