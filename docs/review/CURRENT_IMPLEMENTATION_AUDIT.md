# Current implementation audit

Audit basis: source and tests in the current `main` working tree, not product documentation alone.

| Area | Status | Evidence / boundary |
|---|---|---|
| FastAPI API and Next.js App Router | IMPLEMENTED | `apps/api/main.py`, `apps/web/app`, health/readiness and i18n routes |
| Auth and tenant checks | PARTIAL / PRODUCTION_READY with external OAuth config | `apps/api/dependencies.py`, auth and Google routers; production secrets/domains still required |
| Agent conversations, SSE, citations, tools, attachments | IMPLEMENTED | `apps/api/services/agent_service.py`, `packages/agents/chat/tools.py` |
| Default LLM, DeepSeek, Luna, Mock provider | PARTIAL | provider factory and model policy exist; real provider credentials and model availability are external dependencies |
| Credits ledger | IMPLEMENTED / PRODUCTION_READY | append-only `CreditLedger`, persisted reservations/settlements/refunds, reconciliation, idempotency and PostgreSQL/SQLite mutation guards through Alembic `0007` |
| Unified metering | IMPLEMENTED | server-owned quote/reserve/execute/settle/refund lifecycle covers Agent/Luna, reports, notifications, backtests, strategies, signals, previews and user automations; ordinary users cannot submit actual usage |
| Stripe | PARTIAL / BLOCKED_BY_CONFIG | webhook idempotency exists; production Stripe keys/webhook secret and prices required |
| Reports and notifications | PARTIAL | daily reports and channels exist; provider delivery and real credentials are external |
| Portfolio | PARTIAL / BLOCKED_BY_EXTERNAL_CREDENTIAL | API and connectors exist, but NAV is not a universal Decimal/provenance fact layer |
| Risk | PARTIAL | trading/risk routes and PAPER/SHADOW controls exist; deterministic full risk engine is not implemented |
| Backtest | MOCK_ONLY for Nautilus mock path | mock engine is explicitly labeled in tests; do not use as live performance evidence |
| Trading | PARTIAL / PRODUCTION_READY only for PAPER/SHADOW boundaries | LIVE, withdrawal and transfer are disabled; execution/reconciliation require runtime and exchange evidence |
| Realtime analytics pipeline | NOT_IMPLEMENTED | no unified event bus/checkpoint/replay/DLQ contract |
| Trading MCP | NOT_IMPLEMENTED | no `apps/trading-mcp` service in current tree |
| Frontend fallback | PARTIAL | production API failures carry `unavailable` and mock fallback is disabled; hidden P2+ pages still need complete stale/partial status UX before exposure |
| Deployment | BLOCKED_BY_CONFIG | production images and single-host Compose were built and smoke-started locally; real secrets, DNS/TLS, backup/restore and the final Japan/China/Mac topology remain deployment-host work |
