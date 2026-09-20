# PureGamma Harness

PureGamma Harness is the target runtime and product identity for the PureGamma refactor.

The product is no longer treated as a monolithic Next.js + FastAPI application.
PureGamma Harness is a DeepSeek Harness distribution/profile with a deliberately
thin shell:

- PureGamma Harness logo/brand plugin
- Harness conversation surface
- Cordis profile/composition

Everything else is a plugin. The existing `apps/web`, `apps/api`, Python
packages and external runtimes remain migration sources/providers until each
capability crosses its parity gate.

## Pinned upstream runtimes

PureGamma Harness pins both upstream runtimes as git submodules:

```text
vendor/deepseek-harness
  c291e7961a515f6d7af9304e7fd1d257929aef26

vendor/pg-tsy-core-bootstrap
  d7e719b0b2815a1069df9cb4e25c49946dead699
```

DeepSeek Harness supplies the runtime/build contract. `pg-tsy-core-bootstrap`
remains an independent Rust quantitative trading runtime and is consumed through
its own Cordis Service Definition/provider plugin.

Do not copy runtime internals into PureGamma Harness. A runtime upgrade is an
explicit submodule bump followed by compatibility build/tests.

## Everything is a plugin

The complete capability inventory is machine-readable in `plugins/catalog.ts`.
Top-level plugin families are:

```text
Auth
Agent Chat
Market Data
Data Sources
Research
Research Runner
Secretary
Skills
Portfolio / NAV
Portfolio Autopilot
Options
Backtest
Memory
Trading
Trading Mandates
Nautilus Runtime
pg-tsy Runtime
Notifications
Billing / Credits / Wallet
API Gateway / Model Router
Mobile API
Admin / Plugin Inventory
```

Vendor/provider boundaries underneath those families are plugins too: Plaid,
IBKR, Hyperliquid, Binance, EVM/Moralis, Deribit, Polygon, RSS/ChainCatcher,
X/Bloomberg-style sources, Stripe, Telegram, Slack, APNs, iMessage, Nautilus and
pg-tsy must never be shell dependencies.

## Target composition

```text
Cordis kernel
  + DeepSeek Harness
      + dsh-base
      + dsh-web-app
      + @puregamma/harness-profile
          + @puregamma/dsh-ui-brand
          + PureGamma service definition plugins
          + replaceable provider plugins
          + model-facing tool plugins
          + client UI/slot plugins
          + background worker plugins
          + external runtime adapter plugins
```

The shell contains no Portfolio, Research, Options, Trading, Billing or Admin
implementation. Removing a capability plugin must remove its services, tools,
background work and UI contributions without editing the shell.

## Migrated vertical slices

### Market Data

```text
Harness Agent
  -> market_snapshot / market_news / market_provider_health
  -> ctx.pgMarketData
  -> @puregamma/dsh-market-data-legacy-api
  -> temporary compatibility FastAPI endpoints
```

### Portfolio / NAV

```text
Harness Agent
  -> portfolio_snapshot / portfolio_positions / portfolio_nav
  -> ctx.pgPortfolio
  -> @puregamma/dsh-portfolio-legacy-api
  -> authenticated compatibility /portfolio endpoint
```

No connected account is represented as unavailable rather than a fabricated
zero portfolio. Compatibility reads do not silently trigger billable vendor
refreshes.

### pg-tsy quantitative runtime

```text
Harness Agent
  -> quant_runtime_status
  -> ctx.pgTsyRuntime
  -> @puregamma/dsh-pg-tsy-runtime-http
  -> pg-tsy /healthz or /readyz
  -> pg-core --serve (Rust)
```

The lower-level provider also understands pg-tsy's `/admin/reload` control call,
but strategy reload is disabled by default and is not exposed as an unrestricted
model tool. Installing the plugin never enables live trading.

## Build

From the repository root:

```bash
git submodule update --init --recursive
corepack enable
pnpm --dir vendor/deepseek-harness install --frozen-lockfile --ignore-scripts
pnpm --dir harness install --no-frozen-lockfile
pnpm --dir harness run check
```

`pnpm run check` runs an architecture guard before TypeScript/build. It rejects:

- direct `harness/plugins/*` imports from legacy `apps/`, `packages/` or `services/`;
- creation of a second Cordis root with `new Context()`;
- plugin packages outside the `@puregamma/dsh-*` namespace;
- profile dependencies that are not PureGamma Harness plugins.

GitHub Actions runs `.github/workflows/harness-v2.yml`, displayed as
**PureGamma Harness**, verifies both pinned submodules, checks the Harness client
bundle contract and verifies migrated service/provider/tool artifacts.

## Non-negotiable architecture rules

1. **Cordis owns lifecycle and dependencies.** PureGamma Harness never grows a
   second plugin runtime.
2. **The shell owns zero business capability.** The product shell is branding,
   conversation and composition only.
3. **Consumers depend on Service Definitions, not providers.** Vendors/runtimes
   are replaceable.
4. **UI is a plugin contribution.** New domain UI uses Harness slots/tool views/
   resources, never a shell-owned finance route.
5. **Workers are plugins.** Schedules, queues, sync loops and automation must be
   lifecycle-owned and disappear with their plugin.
6. **Python/Rust processes are provider runtimes.** Pluginization is an ownership
   and lifecycle boundary, not a forced language rewrite.
7. **Trading stays fail-closed.** Plugin migration must preserve idempotency,
   UNKNOWN recovery, reconciliation, kill switches, mandate/approval gates,
   ownership checks and immutable ledger semantics.
8. **Legacy is temporary.** New business functionality lands only under
   `harness/plugins/*` or an intentionally pinned provider runtime.

## Directory ownership

- `profile/` — the PureGamma Harness profile overlay.
- `plugins/` — PureGamma Harness service/provider/tool/client plugin packages.
- `scripts/` — architecture/build guards, not product business logic.
- `../vendor/deepseek-harness` — pinned Harness runtime/build toolchain.
- `../vendor/pg-tsy-core-bootstrap` — pinned Rust quant runtime provider source.
- `../apps/web`, `../apps/api`, `../packages`, `../services` — migration inputs /
  compatibility surfaces only.

See `docs/architecture/HARNESS_CORE_V2.md` for the full migration map and
acceptance criteria.
