# Production blockers

P0 blockers before accepting real users:

1. Supply strong `JWT_SECRET`/`SESSION_SECRET`, `ENCRYPTION_MASTER_KEY`, `NAUTILUS_RUNTIME_SECRET`, Postgres password, Redis URL, Stripe secrets and HTTPS domains. Startup validation must pass.
2. Repeat the verified production Compose smoke on the target host with real secrets, DNS and TLS; Docker Desktop CLI path compatibility is handled by the smoke script.
3. Keep `BILLING_MODE=stripe`, demo login/fallback and mock data disabled in production.
4. Configure a real market/portfolio provider and verify freshness; no mock result is valid for Portfolio, Risk or Trading.
5. Alembic empty-Postgres upgrade is verified through `0007`; Postgres backup/restore and runtime-state restore drills remain mandatory before real users.

P1 commercial metering status: **implemented and locally verified**.

* authenticated users may call Quote, Ledger, Budget and Reward-history APIs;
* reservation, settlement, refund and actual usage remain server-owned and are intentionally not public APIs;
* all identified user-paid Agent/report/notification/backtest/strategy/signal/preview/automation paths use the persisted state machine;
* ledger reconciliation, concurrency, duplicate settlement/refund, provider refund and automation-budget tests pass;
* real provider token/accounting comparisons remain an operational staging check, not a code-path blocker.

P2+ blockers:

* deterministic Portfolio fact layer and Risk Engine;
* Redis Streams event pipeline with replay/DLQ;
* Global Agent Tool Registry artifacts;
* Trading MCP with challenge confirmation and runtime reconciliation.
