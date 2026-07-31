# PureGamma AI Release Checklist

Use this checklist before promoting a build to staging or production.

## Test Commands

- Backend dependencies installed from `apps/api/requirements.txt`.
- `pytest` passes with no unexpected failures.
- Python lint/type checks pass if the toolchain is installed.
- Frontend dependencies installed in `apps/web`.
- `npm run typecheck` passes.
- `npm run lint` passes.
- `npm run build` passes.
- `npm run test:e2e` passes after Playwright browsers are installed.

## Billing And Credits

- Stripe webhook signature validation enabled in Stripe mode.
- Duplicate `invoice.paid` does not grant duplicate credits.
- Duplicate webhook event ID is idempotent.
- `checkout.session.completed` cannot grant a forged plan from client input without trusted Stripe state in Stripe mode.
- `customer.subscription.deleted` downgrades to Free.
- `invoice.payment_failed` restricts high-cost tasks.
- Credit ledger balance matches user balance after grants, consumption, and refunds.

## Notifications

- Email, Telegram, Slack, and iMessage mock send paths work.
- iMessage HMAC validation rejects invalid signatures and stale timestamps.
- Duplicate idempotency keys do not send twice or charge twice.
- Free and Pro users cannot send iMessage.
- Max and Enterprise users can send iMessage when credits and daily rate limits allow it.
- Provider failure refunds consumed credits and does not fail report generation.

## Portfolio And Integrations

- Portfolio NAV service tests pass for Plaid-only, CEX-only, wallet-only, mixed sources, stablecoins, stale prices, partial data, allocation, daily PnL, unrealized PnL, concentration risk, BTC beta, and duplicate-source handling.
- Sync failure does not overwrite the last valid NAV snapshot.
- Plaid access tokens are encrypted and never returned by API responses.
- Exchange API keys are encrypted and never returned by API responses.
- Private keys and seed phrases are rejected.
- Wallet ownership is scoped to the authenticated user.

## Data Pipeline And AI

- CoinDesk, RSS, X KOL, Bloomberg mock, and market providers are tested in mock mode.
- Duplicate articles/posts are deduped by stable content hash.
- Data source success/failure status is persisted.
- UI never displays deterministic NAV when data is partial or stale.
- LLM provider mock works without API keys.
- High-cost sources require entitlement.

## Nautilus / Trading Guardrails

- Live trading is disabled by default.
- `NAUTILUS_LIVE_TRADING_ENABLED=false` blocks order submission.
- `NAUTILUS_ALLOW_LIVE_ORDER=false` blocks order submission.
- Free users cannot use Nautilus.
- Pro users are limited to mock backtests.
- Max users can use advanced backtests.

## Deployment Checks

- Production secrets are present only in the deployment secret store.
- No secret values are logged or exposed in API responses.
- Database migrations are reviewed and reversible.
- Redis/Celery worker and scheduler health checks are green.
- Stripe webhook endpoint uses raw body verification.
- Observability dashboards cover API errors, webhook errors, notification failures, worker failures, and LLM/provider spend.

## Release Decision

Do not release to Beta if any of these are unresolved:

- Unexpected pytest failures.
- Failed billing replay/idempotency tests.
- Failed tenant isolation or secret redaction tests.
- Failed live trading disabled tests.
- Missing executable portfolio NAV correctness tests.
- Any Sev-1 or Sev-2 bug without an accepted mitigation.
