# Deployment Checklist

- Set `APP_ENV=production`, a high-entropy `SESSION_SECRET`, HTTPS web/API origins, and exact CORS origins.
- Back up PostgreSQL, run `python -m scripts.db_migrate check`, then apply `python -m scripts.db_migrate upgrade`; verify `alembic current` reports head.
- Configure Google client ID/secret and every localized callback URI.
- Configure one real Agent provider/model/key and keep `ENABLE_MOCK_AGENT=false`.
- Set `AGENT_GLOBAL_CONCURRENT_RUNS` for the VPS capacity and run exactly one scheduler instance.
- Confirm Max is not advertised with priority execution until Agent runs move to a real worker queue.
- Keep `ENABLE_MOCK_DATA_SOURCES=false`; configure public provider flags and reviewed RPC/subgraph URLs.
- Run API, Redis, Celery worker, and the existing APScheduler as separate supervised processes.
- Configure Stripe key, price IDs, signed webhook secret, and production success/cancel URLs.
- Confirm notification credentials and iMessage relay HMAC secret where enabled.
- Run the iMessage Relay on a separate Mac reachable over WireGuard/private networking; never expose port 8787 publicly.
- Set iMessage verification request limits and alert on repeated verification throttling.
- Restrict admin users, rotate development credentials, and do not copy `.env` into images.
- Run `pytest`, `pnpm typecheck`, `pnpm build`, and browser smoke tests.
- Verify `/health`, `/admin/data-sources`, Google login/logout, `/chat`, Stripe webhook idempotency, and notification delivery.
- Monitor provider `RATE_LIMITED`/`ERROR`, stale sync runs, Agent failed/interrupted runs, token usage, credit ledger, and Stripe webhook errors.
- Alert on `/health` degradation, overdue notification retries, and daily brief delivery gaps; back up PostgreSQL daily and test restores.
