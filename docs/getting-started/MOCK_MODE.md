# Mock Mode

Mock mode lets developers and product reviewers run PureGamma AI without real Stripe, market-data, notification, Plaid, exchange, wallet, Bloomberg, or Nautilus credentials.

Mock research content is not financial advice and must not be used as live investment input.

## Core Settings

```text
BILLING_MODE=mock
IMESSAGE_PROVIDER=mock
AUTH_ALLOW_DEMO_FALLBACK=false
```

## What Is Mocked

| Area | Mock behavior |
| --- | --- |
| Billing | Checkout returns a local mock URL; portal returns a mock URL. |
| Subscription | `POST /billing/mock-upgrade` upgrades the current user and grants credits. |
| Auth | `POST /auth/mock-login` creates a local HMAC-signed bearer token. |
| Market data | `MockMarketDataProvider` returns BTC, ETH, SOL, HYPE, MSTR, STRC data. |
| Email | Missing SMTP host returns mock success. |
| Telegram | Missing token or mock recipient returns mock success. |
| Slack | Missing or mock webhook returns mock success. |
| iMessage | `IMESSAGE_PROVIDER=mock` records a sent mock delivery. |
| Portfolio | Frontend returns fallback NAV and positions. |
| Integrations | Frontend returns fallback connector rows. |
| Data sources | Frontend returns fallback health rows. |
| Nautilus | Frontend returns fallback strategy metrics; backend `/backtest` uses mock engine. |

## Mock Login

```bash
curl -X POST http://localhost:8000/auth/mock-login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@puregamma.ai","name":"Demo User"}'
```

The server does not accept a role from the client. The seeded `demo@puregamma.ai` user is admin for local demos.

## Mock Upgrade

```bash
curl -X POST http://localhost:8000/billing/mock-upgrade \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan_name":"Max"}'
```

This is available only when `BILLING_MODE=mock`.

## Mock iMessage

```bash
curl -X POST http://localhost:8000/notifications/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel":"imessage","message":"Demo message. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.","metadata":{"idempotency_key":"demo-imessage-1"}}'
```

If the user is not entitled to iMessage, the delivery is skipped with `entitlement_denied`.

## Production Warnings

- Do not enable `AUTH_ALLOW_DEMO_FALLBACK` in production.
- Do not use mock market data for customer-facing live claims.
- Do not use mock billing to grant production access.
- Do not represent fallback Portfolio NAV as synced portfolio data.
- Do not enable iMessage relay without HMAC secret, network controls, and delivery audit.
