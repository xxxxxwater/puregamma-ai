# Production Checklist

Use this checklist before exposing PureGamma.ai to real users or enterprise customers.

## Product and Compliance

- Investment disclaimer appears on reports, signals, playbooks, backtests, NAV pages, and notifications.
- Portfolio NAV is labeled as estimate, not official statement.
- Backtests are labeled hypothetical and not predictive.
- No UI copy promises profit, returns, alpha, or guaranteed outcomes.
- Terms, privacy policy, and support contact are ready.

## Security

- `JWT_SECRET` is high entropy and not the default.
- `AUTH_ALLOW_DEMO_FALLBACK=false`.
- All secrets are stored in a secret manager.
- Admin endpoints are protected and admin users are reviewed.
- Stripe webhook signature verification is enabled.
- iMessage relay has a unique HMAC secret and private network exposure.
- Exchange keys are read-only only; no withdrawal or trading permissions.
- Plaid and exchange credentials will be encrypted before persistence when those features are implemented.

## Infrastructure

- Managed Postgres with backups, point-in-time restore, and TLS.
- Redis with authentication and TLS.
- API health checks configured.
- Worker and scheduler processes supervised.
- Logs and metrics shipped to observability stack.
- Error reporting scrubs secrets and PII.

## Billing

- `BILLING_MODE=stripe`.
- Stripe products and recurring prices exist.
- `STRIPE_PRICE_PRO`, `STRIPE_PRICE_MAX`, and `STRIPE_PRICE_ENTERPRISE` match Stripe dashboard IDs.
- Customer Portal is configured in Stripe.
- Webhook endpoint points to `/stripe/webhook`.
- Duplicate webhooks have been tested.
- Payment failure behavior has been tested.

## Data and Integrations

- Real data providers have rate limits and failure handling.
- Source freshness and stale data warnings are visible.
- Notification providers have test sends and bounce/failure handling.
- iMessage relay tested from API through HMAC-signed request.
- Plaid, exchange, wallet, Bloomberg, and Nautilus features remain disabled until their backend implementation and controls are complete.

## Verification Commands

```bash
curl https://api.example.com/health
python3 -m pytest
```

Stripe webhook:

```bash
stripe listen --forward-to https://api.example.com/stripe/webhook
stripe trigger checkout.session.completed
stripe trigger invoice.paid
stripe trigger invoice.payment_failed
```

## Launch Blockers

Do not launch if:

- Default secrets are still configured.
- Demo fallback auth is enabled.
- Stripe webhook signing is missing.
- Reports or notifications omit disclaimers.
- Admin endpoints are reachable by non-admin users.
- Portfolio NAV is presented as official synced data before backend sync exists.
