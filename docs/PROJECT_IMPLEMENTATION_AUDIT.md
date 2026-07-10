# PureGamma.ai Implementation Audit

## Architecture summary

- Frontend: Next.js App Router, TypeScript, Tailwind CSS, pnpm, localized `/en` and `/zh` routes.
- Backend: FastAPI, SQLAlchemy 2, PostgreSQL in Docker and SQLite for local development/tests.
- Auth: project-owned HS256 JWT plus a partial Google authorization-code flow. Bearer auth is retained for API clients; browser auth is being moved to an HttpOnly cookie.
- Billing: Stripe Checkout, Customer Portal, signed/idempotent webhooks, subscription plans, entitlements, and a credit ledger.
- Workers: the existing Celery app and APScheduler process. Provider synchronization will be added here rather than creating a second scheduler.
- LLM: OpenAI-compatible provider layer with OpenAI and DeepSeek implementations, call logs, and a development mock provider.
- Tests: pytest for backend and Playwright for frontend E2E.

## Existing functionality to reuse

- `apps/api/dependencies.py`: JWT creation/verification and request dependencies.
- `packages/database/models.py`: users, subscriptions, credits, reports, signals, notifications, and LLM call logs.
- `packages/workers`: Celery tasks and APScheduler registrations.
- `packages/agents/llm`: OpenAI-compatible completion providers and usage logging.
- `packages/data/binance_provider.py`: public Binance ticker adapter.
- Existing Stripe, iMessage, reports, signals, account preferences, Dashboard, and admin modules.

## Confirmed gaps

- RSS, DefiLlama, and on-chain modules are placeholders and do not persist normalized records or sync health.
- The Dashboard quote path performs live REST reads but did not persist normalized public-source quotes for Agent retrieval.
- Data Sources UI is backed by hard-coded fallback rows, so disconnected sources can appear healthy.
- Google identity is stored directly on `users.google_user_id`; there is no provider identity table, verified-email timestamp, last-login timestamp, PKCE, nonce validation, revocable browser session, or logout endpoint.
- Browser access tokens are stored in localStorage.
- Existing agents generate reports but have no conversation/message/run tables, controlled tools, SSE stream, citations, cancellation, regeneration, or product usage events.
- There is no formal migration runner. Startup currently uses `create_all` plus compatibility `ALTER TABLE` statements.

## Repeated or dangerous mock behavior

- `packages/data/rss_provider.py`, `defillama_provider.py`, and `onchain_provider.py` return fabricated/static values.
- `packages/agents/llm/provider_factory.py` silently falls back to a mock model when a configured real provider has no key.
- `apps/web/lib/api.ts` silently substitutes mock research and data-source records after API failures.
- Production data-source and Agent paths must instead expose an explicit error/degraded state. Mocks remain available only behind explicit development/test flags.

## Database additions

- Auth: `user_identities`; user verification, login, and session-version columns.
- Providers: `data_sources`, `data_source_sync_runs`, `news_items`, `market_quotes`, `defi_metrics`, `onchain_metrics`.
- Agent: `agent_conversations`, `agent_messages`, `agent_runs`, `agent_tool_calls`, `agent_message_sources`, `usage_events`.
- A forward SQL migration is added under `packages/database/migrations`; startup compatibility remains for existing local databases.

## Files and modules being changed

- Database models/session/migration and seed configuration.
- Unified provider base, RSS, Binance, DefiLlama, EVM RPC, subgraph registry, sync service, worker tasks, and admin routes.
- Google OAuth router, JWT/session dependency, auth serialization, login/callback/account UI.
- Agent service, tool registry, API router, LLM streaming integration, Chat UI, navigation, and frontend API client.
- Data Sources page, admin monitoring, environment example, tests, and delivery documentation.

## Implementation order

1. Add compatible models and a migration.
2. Implement provider request safety, normalization, persistence, health, sync runs, admin APIs, and schedules.
3. Complete Google OIDC identity linking and secure browser sessions.
4. Add Agent persistence, controlled retrieval tools, SSE lifecycle, citations, usage, and Chat UI.
5. Replace hard-coded data-source status, add account/admin views, and run backend/frontend/browser verification.
