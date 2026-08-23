# MVP Upgrade — 2026-07-24

This document records the capabilities delivered after the `upgrade/mvp-20260724`
baseline. It is a product and technical summary, not a claim that every optional
integration is enabled in production.

## What was added

### Research, agent, and personalization

- **Harness Research** provides multi-step, evidence-backed investigations. It
  coordinates specialised market, on-chain, options, and risk research tasks and
  returns validated research artifacts with retained evidence snapshots.
- **Agent memory** adds user-owned, consent-gated memory proposals, scoped
  settings, append-only audits, and expiring conversation summaries. It is used
  only to personalize research context and is never a trading authorization or a
  risk input.
- **Executable strategy specifications** compile declared strategy rules into
  backtests. The agent can access a provenance-carrying tool registry for market,
  journal, and backtest information.
- **Research Runner** runs user research code in a resource-limited, read-only,
  no-network Docker sandbox after static validation.

### Portfolio and trading safety

- **Server-computed NAV** consolidates supported portfolio data and marks stale
  valuations explicitly rather than fabricating a number.
- **LIVE trading control plane** adds a gated, spot-only execution path with
  mandate approval, risk checks, idempotency, kill switches, immutable ledger
  entries, fill synchronization, and daily reconciliation.
- All LIVE controls remain **disabled by default**. The supported operational
  modes are BACKTEST, PAPER, and SHADOW until the documented production gates,
  human approvals, and broker health checks have been satisfied.

### Web, mobile, and delivery

- The web console adds the Ocean/Glass visual system, a classic appearance
  option, research workbench and timeline, capability gates, clearer financial
  stale-state presentation, and a built-in plugin runtime with server-side
  manifest gating.
- **iOS and Android** add capability-gated Research Runs, Memory Controls, and
  Trading Safety. Clients intentionally block LIVE actions and present missing
  endpoints as unavailable instead of showing mock data.
- The Android repository now normalizes Retrofit non-2xx failures into the
  application API exception type, so feature-gating and error handling do not
  depend on interceptor wiring.
- **Photon iMessage** supports verified inbound replies processed asynchronously,
  alongside email, Telegram, Slack, and APNs notification routes.

## Technology and design choices

| Area | Adopted approach |
| --- | --- |
| Application platform | FastAPI API, Next.js web application, SwiftUI iOS client, Kotlin/Compose Android client |
| Research orchestration | Trusted Harness orchestrator plus short-lived low-trust runner; capability-token-gated gateway and evidence snapshots |
| Data and background work | PostgreSQL or local SQLite for development, Redis and Celery for queues, scheduled work, budgets, and reconciliation |
| Trading safeguards | Isolated Nautilus execution runtime, HMAC-signed internal commands, Decimal-based money math, immutable audit/ledger records |
| Client safety | Server capability contract, client-side feature gates, explicit stale/unavailable states, trusted deep links and domain allowlists |
| Plugin architecture | Typed built-in web plugin contracts with runtime services and FastAPI manifest gating |
| Notifications | Asynchronous dispatcher with verified Photon iMessage inbound webhook processing |

## Feature availability

| Capability | Availability |
| --- | --- |
| Agent, backtest, strategies, notifications, billing | Implemented; provider credentials and plan entitlements still apply |
| Harness Research and Memory | Implemented and capability/consent gated; deployment policy controls enablement |
| NAV and Trading Safety APIs | Implemented; stale or unavailable source data is surfaced honestly |
| LIVE spot execution | Implemented as a gated control plane, disabled by default |
| Mobile Research/Memory surfaces | Implemented with unavailable-state fallback; backend rollout is capability controlled |
| Real broker provisioning and store releases | Operational rollout work; not represented as automatically enabled by this upgrade |

## Related documentation

- [Architecture](../developer/ARCHITECTURE.md)
- [Harness Research](../developer/HARNESS_RESEARCH_ARCHITECTURE.md)
- [Memory service](../developer/MEMORY_ARCHITECTURE.md)
- [Mobile API contract](../mobile/MOBILE_API_CONTRACT.md)
- [LIVE trading status](../live-trading/STATUS.md)
- [Photon iMessage integration](../integrations/PHOTON_IMESSAGE.md)
