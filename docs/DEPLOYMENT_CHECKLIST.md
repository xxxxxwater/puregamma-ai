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

## LIVE Trading (实盘控制面)

> 仅当部署实盘能力时逐项核对;默认全部 OFF 时系统恒为 `LIVE_DISABLED`。
> 详见 `docs/live-trading/LIVE_LAUNCH_RUNBOOK.md`(上线顺序与每步回滚)。

- Keep the legacy runtime rails OFF forever: `NAUTILUS_LIVE_TRADING_ENABLED=false`,
  `NAUTILUS_ALLOW_LIVE_ORDER=false`, `NAUTILUS_ALLOW_WITHDRAWAL=false`,
  `NAUTILUS_ALLOW_TRANSFER=false` (production config validation enforces this).
- Keep every LIVE gate OFF (`LIVE_TRADING_ENABLED=false`,
  `LIVE_TRADING_DEPLOYMENT_APPROVED=false`, `LIVE_TRADING_GATEWAY=mock`) until the
  runbook's staged rollout passes each gate; `GET /api/trading/safety-status` must
  read `LIVE_DISABLED` with per-check detail (never fabricated success).
- Set a dedicated `LIVE_CREDENTIAL_ENCRYPTION_KEY` (Fernet) — or rely on a strong
  `ENCRYPTION_MASTER_KEY` (≥32 chars) for derivation; plaintext credentials must
  never exist in the DB, logs, or order acks.
- Real gateway: `LIVE_TRADING_GATEWAY=binance` + `LIVE_TRADING_PROVIDER=binance_spot`;
  rehearse against `LIVE_TRADING_BINANCE_BASE_URL=https://testnet.binance.vision`
  before pointing at `https://api.binance.com`. Keep `LIVE_TRADING_ALLOWED_SYMBOLS`
  to a small whitelist at launch.
- Verify Binance API-key permission hard-check end to end: a key with
  withdrawal/transfer/futures/margin/options enabled must be rejected
  (`UNSAFE_API_PERMISSIONS`) and alert ops.
- Verify submit-timeout semantics once: a timed-out submit becomes an UNKNOWN
  order that is only queried by `puregamma.sync_live_order_statuses` — never
  re-submitted.
- Run `pytest tests/security/test_live_trading_gateway.py` before go-live; confirm
  `alembic current` reports a single head (0026).
- Confirm the scheduled LIVE tasks stay within the single-server budget
  (prices 5–15s, order status 5–10s, balances/NAV 30–60s, reconciliation daily;
  worker concurrency ≤ 2).
- After any server restart, LIVE mandates do NOT auto-resume: verify connection
  health, run `puregamma.daily_live_reconciliation` manually, and only then
  restore mandates.
- Verify `GET /api/frontend/plugins` exposes `puregamma.live-trading` only when
  `LIVE_TRADING_ENABLED=true` (disabled by default).
- Complete and archive `docs/live-trading/FIRST_ORDER_VERIFICATION.md` (first
  order, kill-switch drill, rollback drill) before widening the user whitelist.
