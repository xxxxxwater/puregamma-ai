# Security Overview
PureGamma AI handles investment research data, billing state, notification recipients, and planned portfolio connector data. Treat the system as sensitive even when it does not custody funds.
## Security Principles
- No custody.
- No trading or live order placement in MVP.
- No seed phrases or private keys.
- Exchange keys must be read-only.
- Plaid is investments data only.
- Secrets come from environment or secret manager only.
- Admin access is role-gated.
- User-sensitive data should be minimized, encrypted where appropriate, and deleted on request.
## Current Controls
| Control | Implementation |
| --- | --- |
| Bearer auth | HMAC-signed JWT-like token in `apps/api/dependencies.py` |
| Admin gate | `require_admin` checks `user.role == "admin"` |
| Stripe webhook signing | Enabled when `BILLING_MODE=stripe` |
| Stripe webhook idempotency | `stripe_webhook_events.stripe_event_id` |
| Notification idempotency | `notification_deliveries.idempotency_key` |
| iMessage relay HMAC | `X-PG-Signature` over timestamp and body |
| iMessage rate limit | Per-user daily sent count |
| Credit safety | Row lock on credit consumption |
## Production Gaps
- Add migration framework.
- Add robust auth provider or session management.
- Add tenant/workspace model before enterprise multi-tenant use.
- Add encrypted credential persistence for Plaid/exchange connectors.
- Add audit logs for admin actions.
- Add data deletion workflow.
- Add secret scanning and log scrubbing.
## Required Production Settings
```text
AUTH_ALLOW_DEMO_FALLBACK=false
BILLING_MODE=stripe
NAUTILUS_LIVE_TRADING_ENABLED=false
NAUTILUS_ALLOW_LIVE_ORDER=false
```
## Related Docs
- [Secret Handling](./SECRET_HANDLING.md)
- [Data Privacy](./DATA_PRIVACY.md)
- [Tenant Isolation](./TENANT_ISOLATION.md)
- [iMessage Security](./IMESSAGE_SECURITY.md)
