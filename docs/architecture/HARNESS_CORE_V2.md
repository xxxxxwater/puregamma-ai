# PureGamma Harness Core v2

Status: **active refactor branch** (`refactor/harness-core-v2`)

## Decision

PureGamma is being rebuilt as a **DeepSeek Harness distribution**, not as a
Next.js/FastAPI application that happens to embed Harness.

The permanent shell is intentionally small:

```text
PureGamma profile
  ├─ PureGamma brand
  ├─ Harness conversation
  ├─ Harness session/model/runtime primitives
  └─ plugin loader
```

Every domain capability is an installable Harness/Cordis plugin. The existing
Next.js and FastAPI applications are migration sources and temporary
compatibility surfaces.

## Why the old plugin runtime is not the target

The current frontend runtime in `apps/web/plugins/core` creates its own Cordis
`Context`, manually injects PG services, fetches a FastAPI manifest, then loads
one of a compiled set of built-in frontend plugins. That is useful as an
intermediate architecture but it duplicates facilities that DeepSeek Harness
already owns: profile composition, Loader lifecycle, host/client plugins,
service injection, remotes, credentials, settings, session state and typed UI
slots.

**No new business capability should be added to the old PG frontend plugin
runtime.** It remains only until equivalent Harness plugins have crossed the
migration gate.

## Target capability graph

```text
                      DeepSeek Harness
                            │
                    PureGamma profile
                            │
            ┌───────────────┼────────────────┐
            │               │                │
      MarketData        Portfolio         Trading
       Service           Service           Service
            │               │                │
     providers/tools   providers/tools   risk/execution
            │               │                │
            └──────┬────────┴───────┬────────┘
                   │                │
               Research          Options
                   │                │
                Backtest          Gamma
                   │
              Memory/Skills

     Auth / Billing / Notifications / API Gateway / Admin
                 are plugins on the same runtime
```

## Ownership rules

1. **Service Definition packages own contracts.** Consumers import only the
   contract package.
2. **Provider packages own integrations.** Plaid, IBKR, Hyperliquid, Binance,
   Polygon, Deribit, RSS, X, Bloomberg, Nautilus, etc. never leak into consumer
   imports.
3. **Tool packages own model-facing actions.** A tool is mounted only while its
   required service/provider is healthy.
4. **Client packages own UI contributions.** Business UI is registered into
   Harness slots/tool views/resources. The shell does not gain a Portfolio,
   Trading, Research or Options route.
5. **Python/Rust runtimes are providers, not exceptions.** Existing engines can
   remain out-of-process; a Harness plugin owns their lifecycle/health/RPC.
6. **Backend state remains server-authoritative.** Browser plugins cannot grant
   trading, billing, admin or data entitlements.

## First Service Definitions

The refactor starts with three high-fan-out seams:

- `ctx.pgMarketData` — timestamped/provenance-carrying market/news data.
- `ctx.pgPortfolio` — consolidated positions/cash/NAV with explicit freshness.
- `ctx.pgTrading` — guarded money-moving execution.

Research and Options consume MarketData; Research/Risk consume Portfolio;
Trading consumes all three plus deterministic policy/reconciliation providers.

## Trading invariants that survive the migration

Pluginization is not permission to weaken execution safety. Every
`pgTrading` provider must retain these invariants:

- `clientOrderId` is idempotent across retries and restarts.
- Ambiguous submit transport state becomes `unknown`; it is queried, never
  blindly submitted again.
- Terminal and filled orders remain queryable by client id.
- reduce-only is checked before submission, encoded at the provider/venue
  boundary, and verified again during ownership/reconciliation.
- kill switches prevent new exposure but keep query/cancel/fill recording and
  reconciliation available.
- immutable ledger/reconciliation semantics remain server-side.
- numeric money/quantity crosses the TypeScript seam as decimal strings.

## Migration map

The machine-readable source of truth is `harness/plugins/catalog.ts`.

| Target plugin | Primary legacy source |
| --- | --- |
| `@puregamma/dsh-market-data` | `packages/data`, market/news routers |
| `@puregamma/dsh-research` | `packages/agents`, `packages/harness`, Research frontend plugin |
| `@puregamma/dsh-portfolio` | portfolio code + Portfolio frontend plugin |
| `@puregamma/dsh-options` | `packages/options`, Options frontend plugin |
| `@puregamma/dsh-backtest` | `packages/backtest` |
| `@puregamma/dsh-memory` | `packages/memory` |
| `@puregamma/dsh-trading` | `packages/trading`, `packages/live_trading`, Nautilus runtime |
| `@puregamma/dsh-notifications` | `packages/notifications` |
| `@puregamma/dsh-billing` | `packages/billing` + Stripe API layer |
| `@puregamma/dsh-api-gateway` | `packages/gateway` |
| `@puregamma/dsh-auth` | auth routers/middleware |
| `@puregamma/dsh-admin` | admin routes/services/UI |

## Migration sequence

### Slice 0 — runtime skeleton

- Create an isolated refactor branch.
- Add standalone `harness/` workspace.
- Add PureGamma profile overlay.
- Disable official Harness branding and shell sidebar in the PG profile.
- Register PureGamma identity directly in the conversation hero.
- Define capability catalog and cross-plugin contracts.

### Slice 1 — compatibility providers

Wrap the existing backend as providers behind the new service seams. This is a
**one-way dependency**:

```text
Harness consumer -> Service Definition -> compatibility provider -> legacy API
```

Legacy code must never import Harness client packages. Once a native provider
replaces a compatibility provider, the bridge is deleted.

### Slice 2 — read-only finance capabilities

Migrate in this order:

1. MarketData
2. Portfolio/NAV
3. Research
4. Options
5. Backtest
6. Memory

Each capability must ship its tool surface and UI contribution before the old
route is removed.

### Slice 3 — account/product infrastructure

Migrate Auth, Entitlements/Billing, Notifications, API Gateway and Admin into
host/client plugin families.

### Slice 4 — trading control plane

Move execution only after read-side parity exists. Preserve the existing
control-plane gates, immutable ledger, recovery semantics and reconciliation.
The LLM-facing tool layer may request execution but never becomes the authority
that grants it.

### Slice 5 — delete the monolith shell

When all migration gates pass:

- delete the PG-specific browser Cordis runtime;
- remove business navigation/routes from the shell;
- retire FastAPI routers that have native Harness providers;
- keep only required out-of-process finance engines/providers;
- make the Harness profile the production entry point.

## Per-capability migration gate

A legacy capability can be removed only when all are true:

- service contract is versioned and tested;
- provider has explicit health and fail-closed unavailable state;
- model tools are permission/entitlement gated;
- UI comes from a Harness plugin, not shell code;
- restart/reconnect behavior is tested;
- observability identifies plugin + provider + request/session trace;
- security/financial invariants are at least as strong as legacy;
- parity tests cover the legacy behavior being retired.

## Definition of done

The refactor is complete when `puregamma.ai` can be assembled as a Harness
profile where removing a domain plugin removes its model tools, host services,
background work and UI contributions without editing the shell, and the shell
itself contains no finance-domain implementation.
