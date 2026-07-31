# Stripe

PureGamma AI uses Stripe Billing for subscriptions, Checkout Sessions, Payment Links, Customer Portal, webhook-driven subscription state, and monthly credit grants.

## 1. Billing Mode

`BILLING_MODE` controls Stripe behavior:

```text
BILLING_MODE=mock
BILLING_MODE=stripe
```

Use `mock` for local demos. Use `stripe` for real Stripe test mode or production.

## 2. Mock Billing

In mock mode:

- Checkout returns a local mock checkout URL.
- Portal returns a local mock portal URL.
- `POST /billing/mock-upgrade` upgrades the current user.
- Mock upgrade grants monthly plan credits.
- Stripe webhook payloads are parsed without signature verification for local tests.

Example:

```bash
curl -X POST http://localhost:8000/billing/mock-upgrade \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan_name":"Max"}'
```

## 3. Checkout Mode

`BILLING_CHECKOUT_MODE` controls which checkout entrypoint the web billing page uses:

```text
BILLING_CHECKOUT_MODE=session
BILLING_CHECKOUT_MODE=payment_link
```

- `session` calls `POST /billing/create-checkout-session`.
- `payment_link` calls `POST /billing/create-payment-link-checkout`.
- Both paths create a `BillingCheckoutIntent` row before redirecting to Stripe.
- Plan, credits, and entitlements update only from signed Stripe webhooks, never from the success URL.

## 4. Real Stripe Test Mode

Configure:

```text
BILLING_MODE=stripe
BILLING_CHECKOUT_MODE=session
STRIPE_SECRET_KEY=sk_test_...
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_MAX=price_...
STRIPE_PRICE_ENTERPRISE=price_...
STRIPE_PAYMENT_LINK_PRO=https://buy.stripe.com/...
STRIPE_PAYMENT_LINK_MAX=https://buy.stripe.com/...
STRIPE_PAYMENT_LINK_ENTERPRISE=https://buy.stripe.com/...
```

The API pins `STRIPE_API_VERSION` from environment, defaulting to `2026-02-25.clover`.

## 5. Creating Products and Prices

Create one recurring Stripe Price per paid plan:

- Pro.
- Max.
- Enterprise, if self-serve enterprise checkout is supported.

Use recurring Prices, not deprecated Plans.

## 6. Price IDs and Plan Mapping

The code maps plan names to price IDs in `packages/billing/stripe.py` and `apps/api/config.py`.

```text
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_MAX=price_...
STRIPE_PRICE_ENTERPRISE=price_...
```

`config/stripe_plan_mapping.yaml` documents the expected plan-to-price and plan-to-Payment-Link mapping. If a webhook contains an unknown price ID, the new webhook path does not guess the plan; it marks the event and related `BillingCheckoutIntent` as `requires_manual_review`.

## 7. Checkout Sessions

Endpoint:

```text
POST /billing/create-checkout-session
```

Request:

```json
{"plan_name":"Pro"}
```

Behavior:

- Requires bearer auth.
- Creates a Stripe customer if missing.
- Uses `mode=subscription`.
- Creates a `BillingCheckoutIntent` with `checkout_mode=session`.
- Adds `user_id`, `plan_name`, and `checkout_intent_id` metadata to Checkout and Subscription.
- Sets `client_reference_id` to the checkout intent public reference.
- Returns `checkout_url`, `mode`, `checkout_mode`, `checkout_intent_id`, and `price_id`.

## 8. Payment Links

Endpoint:

```text
POST /billing/create-payment-link-checkout
```

Request:

```json
{"plan_name":"Pro"}
```

Behavior:

- Requires bearer auth.
- Creates a `BillingCheckoutIntent` with `checkout_mode=payment_link`.
- Appends `client_reference_id`, `utm_source`, `utm_medium`, and `utm_campaign` to the Payment Link URL.
- Does not put email addresses, API keys, or private metadata into the redirect URL.
- In Stripe mode, normal users must use a plan-specific Payment Link variable such as `STRIPE_PAYMENT_LINK_PRO`.

The optional `STRIPE_PAYMENT_LINK_PRIMARY` is a shared fallback link:

```text
STRIPE_PAYMENT_LINK_PRIMARY=https://buy.stripe.com/7sYbJ1dH6gLX2xq4EvcbC07
```

Because this link's plan mapping is not assumed in code, a completed checkout from the primary link is sent to manual review unless the webhook contains a trusted price ID or explicit plan metadata.

## 9. Customer Portal

Endpoint:

```text
POST /billing/create-portal-session
```

Behavior:

- Requires bearer auth.
- Requires an existing `stripe_customer_id`.
- Returns `portal_url`.

Configure Customer Portal in the Stripe dashboard before production.

## 10. Webhook Endpoint

Endpoint:

```text
POST /stripe/webhook
```

Local test:

```bash
stripe listen --forward-to localhost:8000/stripe/webhook
```

In `BILLING_MODE=stripe`, the webhook requires `STRIPE_WEBHOOK_SECRET` and verifies `Stripe-Signature`.

`STRIPE_WEBHOOK_TOLERANCE_SECONDS` defaults to `300`. Requests with old signature timestamps are rejected before event processing.

## 11. Webhook Events Handled

Implemented in `apps/api/services/billing_service.py`:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`
- `invoice.payment_failed`
- `checkout.session.expired`
- `price.created`
- `price.updated`
- `product.created`
- `product.updated`
- `customer.subscription.trial_will_end`
- `payment_intent.succeeded`
- `payment_intent.payment_failed`
- `charge.refunded`

Webhook rows store `raw_payload_hash`, `requires_manual_review`, and `error_message`. Duplicate Stripe event IDs do not re-run credit grants or subscription changes.

## 12. Product and Price Sync

Admin endpoints:

```text
POST /admin/stripe/products/sync
GET /admin/stripe/products
```

Sync reads active Stripe Products and Prices, maps `Price.lookup_key` or `Price.metadata.plan_name` to `SubscriptionPlan.name`, and updates `stripe_price_id`, `monthly_price`, and `is_active`.

`price.created` and `price.updated` webhooks reuse the same Price-to-plan mapping.

## 13. Manual Review Queue

Manual review is used when Stripe payloads cannot be mapped safely:

- Unknown or missing price ID.
- Shared primary Payment Link without explicit plan metadata.
- Missing known user or checkout intent.
- Subscription update with unknown price mapping.

Admin endpoints:

```text
GET /admin/stripe-events
GET /admin/billing-intents
POST /admin/billing-intents/{intent_id}/resolve
```

Frontend pages:

```text
/admin/stripe-events
/admin/billing-intents
```

Manual resolve requires an admin user, a target user ID, and an explicit plan. Credit grants are idempotent by `manual_resolve_intent_id`.

## 14. Stripe Projects CLI Workflow

Use Stripe Projects only for local workflow state and setup checks. Do not commit `.projects/vault` or generated secrets.

```bash
npx skills add https://docs.stripe.com --list
stripe plugin install projects
stripe projects status --json
```

If the CLI is not authenticated, log in with your Stripe test account and rerun `stripe projects status --json`. Keep webhook endpoint secrets in `.env` or a secret manager, not in docs.

## 15. Testing Duplicate Webhooks

Webhook idempotency uses `stripe_event_id` in `stripe_webhook_events`.

Test by sending the same mock event ID twice in mock mode, or replaying the same Stripe event in test mode. Expected result:

```json
{"processed":false,"duplicate":true,"event_type":"invoice.paid"}
```

Credits must not be double-granted.

## 16. Credit Grants

Credit grants occur on:

- `checkout.session.completed`, unless a monthly grant already exists for that subscription.
- `invoice.paid` when `billing_reason=subscription_cycle`, unless a grant already exists for the invoice ID.
- `POST /billing/mock-upgrade` in mock mode.

Ledger entries use action `monthly_credit_grant`.

## 17. Subscription Cancellation

`customer.subscription.deleted` updates subscription status to `deleted` and moves the user back to `Free`.

`customer.subscription.updated` tracks `cancel_at_period_end`, status, and period timestamps.

Self-service cancellation endpoints:

```text
POST /billing/cancel-subscription
POST /billing/reactivate-subscription
```

## 18. Payment Failure Behavior

`invoice.payment_failed` marks the current subscription as `past_due`. Entitlement logic restricts high-cost tasks when subscription status is `past_due`.

## 19. Troubleshooting

See [Stripe Webhooks Troubleshooting](../troubleshooting/STRIPE_WEBHOOKS.md).

Common checks:

```bash
curl http://localhost:8000/health
stripe listen --forward-to localhost:8000/stripe/webhook
stripe trigger invoice.paid
```

Admin audit:

```text
GET /admin/stripe-events
GET /admin/billing-intents
GET /admin/subscriptions
GET /billing/credits
```
