# Stripe Webhooks Troubleshooting
## Symptoms
- Checkout succeeds but plan remains Free.
- Credits not granted.
- Subscription status stale.
- Webhook returns `400` or `500`.
## Checks
```bash
curl http://localhost:8000/health
stripe listen --forward-to localhost:8000/stripe/webhook
stripe trigger checkout.session.completed
stripe trigger invoice.paid
```
Admin endpoints:
```text
GET /admin/stripe-events
GET /admin/subscriptions
GET /billing/credits
```
## Invalid Signature
Fix:
- Confirm `BILLING_MODE=stripe`.
- Confirm `STRIPE_WEBHOOK_SECRET` matches the endpoint secret from Stripe.
- Ensure the raw request body is passed to Stripe verification.
## Duplicate Event
Expected response:
```json
{"processed":false,"duplicate":true,"event_type":"invoice.paid"}
```
Duplicate events should not grant credits again.
## Missing Credits
Check:
- Event type was handled.
- `invoice.paid` has `billing_reason=subscription_cycle`.
- User can be found by metadata or Stripe customer ID.
- No existing ledger entry already exists for invoice/subscription.
## Payment Failure
`invoice.payment_failed` marks subscription `past_due`. High-cost tasks and iMessage may be restricted.
