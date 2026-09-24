# PureGamma Harness — Everything Is a Plugin

Status: **the trunk, work in progress.** `refactor/harness-core-v2` is the
repository default branch and is currently identical to `main` (`5d0cdea`). The
migration below is not finished — legacy FastAPI routers still serve traffic and
`harness/` is the migration target, not yet the only path. Verified against
`5d0cdea`.

## Architectural decision

PureGamma.ai is being rebuilt as **PureGamma Harness**, a DeepSeek Harness
profile/distribution powered by Cordis. It is not a Next.js/FastAPI monolith
that embeds a plugin runtime.

The permanent product shell is intentionally almost empty:

```text
PureGamma Harness
  ├─ brand/logo plugin
  ├─ Harness conversation surface
  └─ Cordis composition/profile
```

**Everything else is a plugin.** There is no business-domain exception for
backend code, UI, workers, finance engines, data sources, mobile capability
APIs, billing, administration, or trading runtimes.

Design references:

- Cordis: https://github.com/cordiverse/cordis
- DeepSeek Harness: https://github.com/xxxxxwater/deepseek-harness
- Architecture reference supplied for this refactor: https://arxiv.org/abs/2608.25512

## What “everything is a plugin” means here

Cordis is the microkernel. It owns plugin mounting/unmounting, service
dependencies, event wiring and reversible effects. PureGamma Harness does not
create a second privileged application core on top of it.

A former PureGamma capability must become one or more of these plugin roles:

```text
Service Definition  -> stable ctx.<service> contract
Provider            -> concrete vendor/runtime implementation
Tool                -> model-facing action/query
Client/UI            -> Harness slot/tool-view/resource contribution
Worker               -> scheduled/background lifecycle owned by a plugin
Runtime Adapter      -> supervised Python/Rust/external process provider
```

Consumers depend on Service Definitions, never concrete providers. Replacing
Plaid with another portfolio provider, Nautilus with pg-tsy, or a news vendor
with another source must not require editing the PureGamma Harness shell.

## No privileged PureGamma business core

The following are explicitly forbidden as permanent architecture:

- shell-owned Portfolio/Research/Options/Trading pages;
- a global `PureGammaService` or mega FastAPI service imported by plugins;
- a second browser Cordis root or second plugin loader;
- provider SDK types leaking into consumer packages;
- direct UI imports of database/broker/vendor implementations;
- background workers whose lifecycle is not owned by a Cordis plugin;
- a trading runtime that bypasses the Harness service/risk/approval boundaries;
- “temporary” legacy imports becoming dependencies of new Harness packages.

Compatibility providers are allowed only as one-way migration bridges:

```text
Harness consumer
      -> Service Definition
      -> compatibility provider
      -> legacy API/runtime
```

The arrow never points back into Harness.

## Complete PureGamma Harness capability families

The machine-readable source of truth is `harness/plugins/catalog.ts`. The
current target families cover all feature groups documented by the legacy
PureGamma.ai product:

| Capability plugin | Legacy PureGamma functionality being migrated |
| --- | --- |
| `dsh-auth` | Google OIDC, Apple sign-in, email/password, mobile sessions, entitlements bootstrap |
| `dsh-agent-chat` | persistent Agent chat, streaming, citations, tool calls, cancellation, quotas |
| `dsh-market-data` | quotes, Market Wire/news, source attribution, freshness |
| `dsh-data-sources` | provider catalog, health, source entitlements/admin configuration |
| `dsh-research` | research orchestration, evidence snapshots, artifacts, sub-agent workflows |
| `dsh-research-runner` | no-network sandboxed research code execution |
| `dsh-secretary` | Private Secretary, daily brief, voice/TTS, automation orchestration |
| `dsh-skills` | declarative skills, tool whitelists, deterministic workflows |
| `dsh-portfolio` | accounts, positions, Plaid/IBKR/Hyperliquid aggregation, server NAV |
| `dsh-portfolio-autopilot` | scheduled portfolio reviews, concentration/freshness findings |
| `dsh-options` | Deribit/Polygon chains, surfaces, Long Gamma candidates |
| `dsh-backtest` | strategy compiler, unified backtests, metrics/artifacts |
| `dsh-memory` | scoped user memory, proposals, consent, audit, TTL summaries |
| `dsh-trading` | preview/submit/cancel, risk, execution, ledger, reconcile, kill switch |
| `dsh-trading-mandates` | mandates, dual confirmation, pause/resume, approvals, release refs |
| `dsh-nautilus-runtime` | existing Nautilus PAPER/SHADOW/BACKTEST execution provider |
| `dsh-pg-tsy-runtime` | pg-tsy Rust market/strategy/risk/OMS/execution/reconcile runtime provider |
| `dsh-notifications` | email, Telegram, Slack, APNs, iMessage relay/inbound routing |
| `dsh-billing` | Stripe, plans, credits, entitlements, reservations, gateway wallet |
| `dsh-api-gateway` | OpenAI-compatible gateway, model catalog/router, keys, RPM, usage/pricing |
| `dsh-mobile-api` | capabilities, deep links, push routing and mobile compatibility contract |
| `dsh-admin` | users, data-source health, billing/gateway approvals, trading admin, plugin inventory |

Provider integrations underneath these families are plugins too. Examples:
Plaid, IBKR, Hyperliquid, Binance, EVM/Moralis, Deribit, Polygon, ChainCatcher,
RSS, X, Bloomberg, CoinGecko, Coinglass, Glassnode, DefiLlama, Stripe, Telegram,
Slack, APNs, iMessage/Photon, Nautilus, and pg-tsy.

## Plugin tree shape as built

The families above are the target taxonomy. The tree on disk
(`harness/plugins/`, 58 packages at `5d0cdea`) is organized in four layers, which
is worth knowing before reading the directory:

| Layer | Count | Naming | Role |
| --- | ---: | --- | --- |
| Service / feature | 23 | `<domain>` | Cordis service definitions and their implementations |
| Legacy compatibility | 15 | `<domain>-legacy-api` | one-way bridges to the FastAPI routers being retired |
| Model-facing tools | 16 | `tool-<domain>` | permission- and entitlement-gated tools the Agent may call |
| Client / UI | 4 | `ui-<domain>` | UI contributions mounted by plugins, not by the shell |

The 23 service/feature plugins are: `admin`, `api-gateway`, `auth`, `backtest`,
`billing`, `brand`, `client-remotes`, `data-sources`, `market-data`, `memory`,
`notifications`, `options`, `pg-tsy-runtime`, `pg-tsy-runtime-http`, `portfolio`,
`research`, `research-runner`, `rsi-orchestrator`, `secretary`, `skills`,
`trading`, `trading-mandates`, `trading-observation`.

Two of those are not yet represented as families in the table above:

- **`rsi-orchestrator`** — RSI memory orchestration, see
  [rsi-memory-orchestration.md](../../harness/docs/rsi-memory-orchestration.md).
- **`trading-observation`** — the read-only trading observation contract,
  deliberately isolated from execution so an observation path can never reach
  order submission. See
  [JEV_INTEGRATION.md](../../harness/docs/JEV_INTEGRATION.md).

`brand` and `client-remotes` are shell-level plugins rather than capability
families.

## Runtime composition

```text
                         Cordis kernel
                              │
                     DeepSeek Harness
                              │
                    PureGamma Harness profile
                              │
        ┌─────────────────────┼────────────────────────┐
        │                     │                        │
   Service plugins       Provider plugins          UI/tool plugins
        │                     │                        │
        │         ┌───────────┴────────────┐           │
        │         │                        │           │
  pgMarketData  pgPortfolio           pgTsyRuntime    │
        │         │                        │           │
     vendors   Plaid/IBKR/...     pg-tsy Rust core    │
        │         │                        │           │
        └─────────┴──────────┬─────────────┘           │
                            │                         │
                     Research / Risk / Trading <─────┘
```

A plugin disappearing must remove its services, tools, jobs and UI contributions
without editing the shell. A dependent plugin uses Cordis dependency injection
and transitions out when its required service disappears.

## pg-tsy-core-bootstrap as a first-class plugin runtime

`xxxxxwater/pg-tsy-core-bootstrap` is pinned as a git submodule (see
`.gitmodules`) at:

```text
vendor/pg-tsy-core-bootstrap
commit f5a6382438d8a85e282da5d58d22af9fe5887ca3
```

It remains an independent Rust runtime. PureGamma Harness does **not** copy its
crates into TypeScript. The Cordis boundary is:

```text
@puregamma/dsh-pg-tsy-runtime            # Service Definition
              │
@puregamma/dsh-pg-tsy-runtime-http       # provider
              │
       /healthz /readyz /admin/reload
              │
      pg-tsy-core --serve (Rust)
```

The current pg-tsy HTTP control listener is intentionally narrow. The Harness
provider therefore exposes health/readiness and an explicit strategy-reload
service call; strategy reload is disabled by default. Installation does not
turn on live trading and does not add any model-facing submit/cancel/flatten
shortcut.

Money-moving pg-tsy execution will integrate behind the same deterministic
`pgExecution` / `pgRisk` / `pgReconciliation` / mandate/approval services as
other execution providers. The model may request an action; it never grants the
authority for it.

## Current migrated vertical slices

### MarketData

```text
Harness Agent
  -> market_snapshot / market_news / market_provider_health
  -> ctx.pgMarketData
  -> @puregamma/dsh-market-data-legacy-api
  -> temporary FastAPI compatibility endpoints
```

### Portfolio/NAV

```text
Harness Agent
  -> portfolio_snapshot / portfolio_positions / portfolio_nav
  -> ctx.pgPortfolio
  -> @puregamma/dsh-portfolio-legacy-api
  -> authenticated legacy /portfolio snapshot
```

No connected account is represented as unavailable (`nav = null` at the service
seam), never as a fabricated zero portfolio. Compatibility reads do not silently
trigger billable Plaid refreshes.

### Quant runtime / pg-tsy

```text
Harness Agent
  -> quant_runtime_status
  -> ctx.pgTsyRuntime
  -> @puregamma/dsh-pg-tsy-runtime-http
  -> pg-tsy /healthz or /readyz
```

The source runtime is pinned as a submodule and verified by CI.

## Trading invariants that survive every plugin migration

Pluginization is not permission to weaken financial safety. Every execution
provider must preserve these invariants:

- stable `clientOrderId` idempotency across retries and restarts;
- ambiguous external submission becomes `UNKNOWN`, then reconcile/query — never
  blind replacement submission;
- terminal/filled orders remain discoverable by client identity;
- reduce-only is validated before submission and verified during ownership and
  reconciliation;
- kill switches block new exposure but not query/cancel/fill recording/reconcile;
- immutable ledger history is never rewritten;
- reconciliation and venue truth remain server-side authorities;
- credentials never enter browser/client plugin state;
- money/quantity crosses JavaScript boundaries as decimal strings;
- live trading requires deterministic gates independent of LLM output.

## Migration sequence

### Slice 0 — PureGamma Harness skeleton

Completed/active:

- isolated refactor branch;
- pinned DeepSeek Harness upstream;
- `harness/` workspace and profile overlay;
- PureGamma Harness logo/brand plugin;
- conversation-first shell with business navigation removed;
- capability catalog and service contracts;
- isolated CI build gate.

### Slice 1 — read-side compatibility providers

1. MarketData — implemented first vertical slice.
2. Portfolio/NAV — compatibility provider/tool slice implemented.
3. pg-tsy runtime health/readiness — provider/tool slice implemented.
4. Research.
5. Options.
6. Backtest.
7. Memory.

### Slice 2 — agent/product plugins

Migrate Agent Chat, Research Runner, Secretary, Skills, Portfolio Autopilot,
Data Sources and Mobile API capability surfaces.

### Slice 3 — account/commercial infrastructure

Migrate Auth, Billing/Entitlements/Wallet, Notifications, API Gateway and Admin.
All scheduled jobs and workers move under plugin-owned lifecycle scopes.

### Slice 4 — execution runtimes and LIVE control plane

- expose Nautilus as a replaceable runtime provider;
- extend pg-tsy with the stable control/runtime API required by Harness;
- migrate mandates, approvals, risk, ledger, reconciliation and kill switches;
- add native Hyperliquid/IBKR execution provider wiring only behind those gates;
- preserve venue idempotency/UNKNOWN recovery semantics;
- remove compatibility execution paths only after shadow/paper/canary parity.

### Slice 5 — delete the monolith

When every migration gate passes:

- delete `apps/web/plugins/core` and the old browser plugin runtime;
- remove shell-owned finance routes/navigation;
- retire FastAPI routers/services whose ownership has moved to native plugins;
- keep Python/Rust processes only where they are intentionally provider
  runtimes;
- make the PureGamma Harness profile the production entry point.

## Per-capability migration gate

A legacy capability can be removed only when all are true:

- Service Definition is versioned and tested;
- provider has explicit health and fail-closed unavailable state;
- required services are declared through Cordis dependency injection;
- all external resources are lifecycle-owned/reversible effects;
- model tools are permission/entitlement gated;
- UI comes from a Harness client plugin, not shell code;
- background jobs are mounted/unmounted with their owning plugin;
- restart/reconnect behavior is tested;
- observability identifies plugin + provider + request/session trace;
- financial/security invariants are at least as strong as legacy;
- parity tests cover the legacy behavior being retired.

## Definition of done

The refactor is complete only when PureGamma Harness can be assembled entirely
from its profile and plugin tree, and removing any domain plugin removes that
capability's host services, tools, jobs, provider connections and UI without a
shell code change.

The shell itself must contain **zero finance-domain implementation**.
