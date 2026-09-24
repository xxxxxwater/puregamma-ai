# Target architecture

This document states the architecture PureGamma AI is converging on. It is the
concise contract that the rest of the system is measured against; for the
current workspace layout and verified gaps, see
[Architecture](../developer/ARCHITECTURE.md). Verified against `5d0cdea`.

## The governing pipeline

```text
API
 -> policy / entitlement
 -> metering quote / reservation
 -> deterministic service
 -> evidence / artifact
 -> LLM explanation
 -> metering settlement or refund
```

Every request path follows this order. The properties that matter:

- **Policy and entitlement decide before work happens.** No model and no service
  call is reachable without passing the gate.
- **Metering is quoted and reserved before the deterministic service runs**, then
  settled or refunded — never charged retroactively on success only.
- **The deterministic service owns the facts.** It produces the
  evidence/artifact that the answer is grounded in.
- **The LLM only explains.** A model may narrate, summarise, or propose; it
  never authorizes, prices, or executes. No model bypasses policy or billing.

## Layer responsibilities

**Portfolio is the fact layer.** Connectors produce idempotent,
provenance-tagged `Decimal` snapshots. Money never crosses a boundary as a
float. A missing or stale valuation is reported as unavailable (`nav = null`),
never fabricated as zero, and every snapshot records its price timestamp and
calculation version.

**Risk consumes only fresh, non-mock snapshots** and returns deterministic
assessments. It does not invent inputs: if the data is stale or mock, risk
refuses rather than degrades silently.

**Trading requests pass permission, freshness, instrument and risk gates**
before a one-time confirmation reaches the execution runtime. The model may
request an action; it never grants the authority for it. Ambiguous submissions
resolve to `UNKNOWN` and are queried, never blindly retried.

**The Agent Tool Registry is the common surface** for every model tier. Default
and premium models see the same registry and the same gates, so swapping a model
changes the prose, not the permissions.

## Event contract (target)

A **Redis Streams** event contract will carry raw, normalized, enriched and
feature events with checkpoints and a dead-letter queue.

Status: **not built.** There is no `XADD`/consumer-group pipeline and no DLQ in
`packages/workers` or `packages/data` today; scheduled work currently runs
through Celery tasks. Treat the stream contract as a design target, not a
description of the running system.

## Where this is enforced

| Concern | Location |
| --- | --- |
| Policy and entitlements | `packages/billing`, `packages/capabilities` |
| Metering quote/reserve/settle | `packages/billing`, gateway prepaid wallet |
| Deterministic services | `packages/agents`, `packages/reports`, `packages/backtest` |
| Portfolio fact layer and NAV | `packages/data`, `packages/live_trading/nav.py` |
| Risk | `packages/risk`, `packages/live_trading/risk_engine.py` |
| Trading gates and ledger | `packages/live_trading`, `packages/trading` |
| Agent tool registry | `packages/backtest/tools.py`, `packages/skills` |

## Related documentation

- [Architecture](../developer/ARCHITECTURE.md) — current layout and verified gaps
- [Harness Core V2](../architecture/HARNESS_CORE_V2.md) — the plugin migration target
- [LIVE trading architecture](../live-trading/ARCHITECTURE.md)
- [Risk Model](../quant/RISK_MODEL.md)
- [Trading Safety Contract](../trading/TRADING_SAFETY.md)
- [Agent Platform Boundaries](../AGENT_PLATFORM_BOUNDARIES.md)
