# Billing Operations

Billing operations cover Stripe subscriptions, credits, plan entitlements, and payment-failure handling.

## Dashboards and Endpoints

```text
GET /billing/subscription
GET /billing/credits
GET /admin/subscriptions
GET /admin/stripe-events
```

## Normal Checkout Flow

1. User requests `POST /billing/create-checkout-session`.
2. Stripe Checkout completes.
3. Stripe sends `checkout.session.completed`.
4. API upserts subscription and grants monthly credits.
5. Stripe sends recurring `invoice.paid`.
6. API grants monthly credits once per invoice.

## Payment Failure

`invoice.payment_failed` marks subscription `past_due`. Past-due subscriptions restrict high-cost tasks and iMessage.

## Duplicate Webhooks

`stripe_webhook_events.stripe_event_id` prevents double processing. If a duplicate event arrives, API returns `duplicate=true`.

## Manual Support Checks

- Confirm user `stripe_customer_id`.
- Check latest subscription row.
- Check Stripe event row processed state.
- Check `credit_ledger` for grants and consumption.
- Reconcile with Stripe dashboard.

## Do Not

- Manually grant production credits without an audit record.
- Delete webhook events to force replay unless you understand duplicate-credit risk.
- Switch `BILLING_MODE` in production without a maintenance plan.
