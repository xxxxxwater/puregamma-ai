# PureGamma AI Bug Severity Guide

## Sev-1 Critical

Production must stop or be rolled back.

- User A can access User B data.
- Stripe webhook replay grants duplicate credits or changes the wrong user plan.
- Plaid access token, exchange key, private key, seed phrase, or Stripe secret is exposed.
- Live trading or order submission is enabled unexpectedly.
- Portfolio NAV is materially wrong without a visible partial/stale warning.
- Billing or credit ledger corruption affects multiple users.

## Sev-2 High

Release is blocked unless there is an explicit mitigation.

- A user can bypass plan entitlement for Max-only features.
- Payment failure does not restrict high-cost tasks.
- iMessage/Slack/Telegram/email sends duplicate notifications for the same idempotency key.
- Provider failure causes report generation to fail instead of only failing delivery.
- High-cost data source or LLM call can run without entitlement or budget guardrails.
- Admin endpoint is reachable by a non-admin user.
- Webhook signature validation accepts invalid or stale payloads in production mode.

## Sev-3 Medium

Fix before release if user-facing or affecting financial interpretation.

- Data source failure is not reflected in source status.
- Stale prices are not labeled in portfolio views.
- Missing KOL or financial advice disclaimers.
- Retry count, delivery status, or ledger metadata is inaccurate.
- E2E workflow regression blocks upgrade, sync, or report preview in common browsers.

## Sev-4 Low

Fix in the normal backlog.

- Cosmetic UI alignment or copy issues that do not change financial meaning.
- Non-critical admin table sorting/filtering issues.
- Missing optional diagnostics in mock mode.

## Triage Requirements

Every bug report should include:

- Affected user/tenant scope.
- Whether money, credits, secrets, or order routing are affected.
- Reproduction steps.
- Expected vs actual behavior.
- Logs or event IDs where available.
- Whether stale/partial/mock data warnings were visible.
