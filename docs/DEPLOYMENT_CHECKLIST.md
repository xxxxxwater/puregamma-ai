# Deployment Checklist

- Set `APP_ENV=production`, a high-entropy `SESSION_SECRET`, HTTPS web/API origins, and exact CORS origins.
- Use PostgreSQL and apply `packages/database/migrations/0002_public_data_google_agent.sql` once before application rollout. Back up the database first.
- Configure Google client ID/secret and every localized callback URI.
- Configure one real Agent provider/model/key and keep `ENABLE_MOCK_AGENT=false`.
- Keep `ENABLE_MOCK_DATA_SOURCES=false`; configure public provider flags and reviewed RPC/subgraph URLs.
- Run API, Redis, Celery worker, and the existing APScheduler as separate supervised processes.
- Configure Stripe key, price IDs, signed webhook secret, and production success/cancel URLs.
- Confirm notification credentials and iMessage relay HMAC secret where enabled.
- Restrict admin users, rotate development credentials, and do not copy `.env` into images.
- Run `pytest`, `pnpm typecheck`, `pnpm build`, and browser smoke tests.
- Verify `/health`, `/admin/data-sources`, Google login/logout, `/chat`, Stripe webhook idempotency, and notification delivery.
- Monitor provider `RATE_LIMITED`/`ERROR`, stale sync runs, Agent failed/interrupted runs, token usage, credit ledger, and Stripe webhook errors.
