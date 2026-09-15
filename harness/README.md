# PureGamma Harness

PureGamma Harness is the target runtime and product identity for the PureGamma refactor.

The product is no longer treated as a monolithic Next.js + FastAPI application.
PureGamma Harness is a DeepSeek Harness distribution/profile with a deliberately
thin shell:

- PureGamma Harness brand
- conversation surface
- session/model/runtime primitives inherited from DeepSeek Harness
- installable PureGamma Harness capability plugins

Everything domain-specific belongs to a plugin. The existing `apps/web`,
`apps/api`, and Python packages remain as migration sources until a capability
has crossed the compatibility boundary and passed parity tests.

## Pinned upstream runtime

The runtime/build contract is pinned as the git submodule
`../vendor/deepseek-harness`, currently at:

```text
c291e7961a515f6d7af9304e7fd1d257929aef26
```

Do not copy Harness internals into PureGamma Harness. Host-only packages use the
local `nodePlugin()` build preset; browser plugins reuse the pinned upstream
Harness client bundle preset so they emit the required `lib/client.js` factory
format. A Harness upgrade is an explicit submodule bump followed by this
workspace's compatibility build/tests.

## Target composition

```text
DeepSeek Harness
  + dsh-base
  + dsh-web-app
  + @puregamma/harness-profile
      + @puregamma/dsh-ui-brand
      + @puregamma/dsh-auth
      + @puregamma/dsh-market-data
      + @puregamma/dsh-research
      + @puregamma/dsh-portfolio
      + @puregamma/dsh-options
      + @puregamma/dsh-backtest
      + @puregamma/dsh-memory
      + @puregamma/dsh-trading
      + @puregamma/dsh-notifications
      + @puregamma/dsh-billing
      + @puregamma/dsh-api-gateway
      + @puregamma/dsh-admin
```

## Migrated vertical slices

Market data is the first capability crossing the boundary:

```text
Harness Agent
  -> market_snapshot / market_news / market_provider_health
  -> ctx.pgMarketData
  -> @puregamma/dsh-market-data-legacy-api
  -> existing compatibility FastAPI /market/snapshot and /api/news
```

Portfolio/NAV is the next slice and follows the same dependency direction:

```text
Harness Agent
  -> portfolio_snapshot / portfolio_positions / portfolio_nav
  -> ctx.pgPortfolio
  -> compatibility portfolio provider
  -> existing authenticated FastAPI /portfolio
```

Compatibility API dependencies are deliberately temporary and one-way. Replacing
them with native exchange/vendor providers must not change model-facing tools or
plugin consumers.

## Build

From the repository root:

```bash
git submodule update --init --recursive
corepack enable
pnpm --dir vendor/deepseek-harness install --frozen-lockfile --ignore-scripts
pnpm --dir harness install --no-frozen-lockfile
pnpm --dir harness run check
```

The branch also runs `.github/workflows/harness-v2.yml`, displayed in GitHub
Actions as **PureGamma Harness**. It verifies the special Harness client bundle
(`brand/lib/client.js`) and migrated service/provider/tool artifacts.

## Non-negotiable architecture rules

1. **Harness owns the runtime.** Do not create a second browser Cordis root or a
   second plugin loader inside PureGamma Harness.
2. **The shell owns no finance feature.** Portfolio, Research, Trading, Options,
   News, Backtest, Memory, Billing and Admin are plugins.
3. **Plugins depend on service definitions, not providers.** Broker/data/vendor
   implementations are replaceable providers.
4. **UI is a plugin contribution.** New domain UI uses Harness slots/tool views,
   not new top-level product routes in the shell.
5. **Python/Rust services may stay Python/Rust.** Pluginization is an ownership
   and lifecycle boundary, not a forced language rewrite. Long-running engines
   are supervised providers behind typed Harness services.
6. **Trading stays fail-closed.** Moving execution into plugins must not weaken
   idempotency, reconciliation, kill switches, mandate gates, ownership checks,
   or immutable audit/ledger semantics.
7. **Legacy is temporary.** New features must land in `harness/plugins/*`; do not
   add new business functionality to the legacy frontend plugin runtime.

## Directory ownership

- `profile/` — the PureGamma Harness profile overlay.
- `plugins/` — PureGamma Harness plugins and shared service contracts.
- `../vendor/deepseek-harness` — pinned upstream runtime/build toolchain.
- `../apps/web` — legacy/compatibility frontend while migration is in progress.
- `../apps/api` — legacy/compatibility API while migration is in progress.
- `../packages` — existing domain implementations to be wrapped/extracted into
  providers and then retired from direct application ownership.

See `docs/architecture/HARNESS_CORE_V2.md` for the migration map and acceptance
criteria.
