# PureGamma AI Test Strategy

PureGamma AI is tested as a financial data, AI research, subscription billing, and notification system. The QA bar is higher than a generic SaaS app because user trust can be broken by incorrect NAV, duplicate billing credits, cross-tenant data exposure, secret leaks, or accidental live trading.

## Scope

The test suite is organized by risk boundary:

- `tests/unit`: deterministic domain logic, plans, credits, entitlements, risk scores, reports, signals, provider normalization contracts.
- `tests/integration`: FastAPI routes and service flows across database state, billing, Stripe webhooks, notifications, portfolio/integration contracts, data pipeline contracts.
- `tests/security`: tenant isolation, admin access, webhook signatures, secret redaction, live trading guardrails.
- `tests/workers`: scheduler registrations, daily push behavior, market intelligence, report generation, portfolio NAV job contracts.
- `tests/e2e/playwright`: browser checks for dashboard, billing, portfolio, integrations, daily push, Nautilus, and admin workflows.

## Current Implementation Coverage

Implemented and executable coverage:

- Credit ledger consume/grant/refund behavior.
- Free, Pro, Max, Enterprise entitlement behavior.
- Stripe mock checkout, webhook event processing, duplicate event replay prevention, duplicate invoice prevention, subscription update/delete, and payment-failed restriction.
- Notification dispatch for email, Telegram, Slack, and iMessage mock providers.
- iMessage HMAC helpers and Mac relay replay/idempotency behavior.
- Backtest credit spending and entitlement blocking through the mock research engine.
- Reports, signal generation, risk scoring, market provider behavior, scheduler registrations, and worker task control flow.
- FastAPI route access control for current user data and admin endpoints.
- Frontend E2E smoke/regression specs for the risk-critical pages.

## Contract Tests For Missing Product Areas

The repository does not yet contain first-class business modules for these areas:

- Portfolio NAV service and persisted portfolio snapshots.
- Plaid brokerage token lifecycle and holdings/transactions normalization.
- Exchange credential storage and read-only permission validation.
- Wallet address validation and on-chain balance normalization.
- Article/post ingestion storage with content hashes, provider status records, and source run history.
- NautilusTrader live-order API guards beyond the current mock backtest route.

Tests for these areas are present as `xfail` contract tests. They document the expected behavior and should be converted to passing tests when the business modules are implemented.

## Risk-Based Release Gates

Every release must pass these gates:

- Backend: `pytest` with no unexpected failures.
- Billing: Stripe webhook replay and duplicate invoice grant tests pass.
- Security: tenant isolation, admin access, webhook signature, secret redaction, and live trading disabled tests pass.
- Financial correctness: portfolio NAV executable tests pass once the portfolio service is implemented; until then, release cannot be considered Beta QA complete.
- Frontend: typecheck, lint, build, and Playwright E2E pass.
- Cost control: high-cost source/action entitlement tests pass and LLM mock fallback works without API keys.

## Test Data Policy

- Use SQLite in-memory DB for unit and integration tests.
- Use mock external providers by default.
- Never require real Stripe, Plaid, exchange, wallet, Bloomberg, X, OpenAI, Telegram, Slack, email, or iMessage credentials in CI.
- Secret-like values must be asserted redacted from API responses.
- Financial tests must use fixed prices and quantities. No live market data is allowed in correctness assertions.

## Definition Of Done For New Risk Features

Any new billing, credit, portfolio, notification, integration, or trading-related feature must add:

- Unit tests for domain logic.
- Integration tests for API/service/database behavior.
- Security regression tests if the feature touches tenant data, secrets, auth, webhooks, or permissions.
- Worker tests if a scheduler/Celery task can mutate state.
- E2E coverage if the user can trigger or inspect the workflow in the web app.
