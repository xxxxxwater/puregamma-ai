# Audit Before Nautilus Runtime Implementation

Date: 2026-07-10

## 1. Existing Agent request chain

`AgentChat -> POST /api/agent/conversations/{id}/messages -> start_run -> persisted user/assistant/run -> deterministic AgentToolRegistry plan -> OpenAI-compatible provider -> SSE deltas/citations -> persisted tool calls, assistant message and usage event`.

The same router is mounted at `/agent` and `/api/agent`. Conversation ownership is enforced with `user_id`. Existing SSE events and citation persistence are production contracts.

## 2. Existing Agent tools

The allowlist is read-only: persisted market quotes/history, unified RSS/FinTwit/X/Bloomberg documents, legacy DeFi/on-chain metrics, provider status, strategy catalog, and research backtests. No exchange, wallet, signing, withdrawal, transfer, raw HTTP, raw SQL, or shell tool is exposed.

## 3. Existing data-source chain

RSS, FinTwit, official X API, and licensed Bloomberg adapters feed `RawDocument -> NormalizedDocument -> EntityMention/SentimentSignal`. Stable hashes and event fingerprints provide deduplication and provenance. Agent retrieval returns source URLs and timestamps. These records can become strategy features but cannot become orders directly.

## 4. Existing backtest chain

`POST /backtest -> entitlement check -> 25 credit debit -> BacktestEngine -> PureGamma data catalog or synthetic catalog -> optional in-process Nautilus import -> BacktestRun`.

The current engine is primarily a simulation fallback. It has no strategy version, activation, long-running runtime, order journal, account reconciliation, or independent process boundary.

## 5. Existing database model

Implemented domains include users/auth, plans/subscriptions/credits, reports/signals/alerts, notifications, backtests, unified source documents, Agent conversations/messages/runs/tool calls/citations, and usage events. Trading account, strategy version, activation, runtime, order, position, reconciliation, and trading audit models do not exist.

## 6. Existing workers and scheduling

Celery uses Redis; APScheduler schedules shared intelligence, personalized reports, alerts, subscription checks, source sync, and retention cleanup. There is no durable strategy-runtime command queue or reconciliation schedule.

## 7. Existing frontend

Next.js App Router provides localized Chat, Dashboard, Reports, Signals, Playbooks, Billing, Data Sources, Portfolio, Admin, and a Nautilus research page. The Nautilus page is fallback-only and its controls do not call a runtime API.

## 8. Reusable modules

- JWT/cookie authentication and tenant ownership checks.
- Stripe entitlement and credit ledger services.
- Agent SSE and tool-call persistence.
- Unified source provenance and sentiment documents.
- Existing BacktestEngine and metrics.
- Celery/Redis/APScheduler infrastructure.
- Current localized application shell and operational UI components.
- NautilusTrader clone at `../nautilus_trader`, commit `321b534122`, as implementation reference only.

## 9. Gaps

- No control-plane trading domain or approval protocol.
- No independent Nautilus Runtime service/client contract.
- No strategy drafts, immutable versions, risk policies, runs, or audit trail.
- No order-intent/risk-decision boundary or order state machine.
- No paper/shadow exchange, restart recovery, reconciliation, token bucket, or kill switch.
- No strategy/runtime/trading APIs or real frontend runtime state.
- Existing in-process Nautilus import couples backtests to the API process.

## 10. Planned files

- `packages/trading/`: domain enums/schemas, safety policies, control service, runtime client, intent router.
- `services/nautilus-runtime/`: independent FastAPI service, runtime manager, event bus, strategy runner, risk/execution gateways, mock exchange, SQLite state store and reconciliation.
- `apps/api/routers/strategies.py`, `apps/api/routers/trading.py`.
- SQLAlchemy trading models and `0004_nautilus_runtime_control_plane.sql`.
- Frontend strategy/runtime views integrated into the existing app shell.
- Unit, integration, security, state-machine, idempotency, and tenant-isolation tests.
- Runtime, operations, safety, and recovery documentation.

## 11. Core behavior that must not change

- Existing Agent routes, SSE event names, persistence, citations, and research tools.
- Existing `/backtest` behavior when `engine=mock` or the field is omitted.
- Existing RSS/FinTwit/X/Bloomberg pipeline and provenance.
- Existing Stripe, credits, entitlements, OAuth, notifications, workers, and localized UI routes.
- `NAUTILUS_LIVE_TRADING_ENABLED=false` and `NAUTILUS_ALLOW_LIVE_ORDER=false` defaults.
- No custody, withdrawal, transfer, private-key collection, or same-turn execution.

## 12. Phased implementation

1. Add trading domain, models, migration, safety guards, and audit records.
2. Add the independent runtime with Mock Exchange, PAPER/SHADOW modes, order journal, risk checks, idempotency, recovery, reconciliation, and kill switch.
3. Add authenticated tenant-isolated strategy/trading APIs and runtime client.
4. Add Agent intent classification, draft/preview tools, and explicit second-turn confirmation.
5. Connect source provenance to strategy signals and preserve fact/opinion/inference labels.
6. Replace Nautilus fallback UI with strategy/runtime/position/risk views.
7. Add Compose service, configuration, tests, documentation, and end-to-end mock verification.

Live adapters remain interfaces only in this phase. Hyperliquid and Coinbase execution cannot be enabled by Agent input or missing configuration.
