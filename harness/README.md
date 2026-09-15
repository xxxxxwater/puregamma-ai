# PureGamma Harness v2

This directory is the target runtime for the PureGamma refactor.

PureGamma is no longer treated as a monolithic Next.js + FastAPI product. The
new product is a DeepSeek Harness distribution/profile with a deliberately thin
shell:

- PureGamma brand
- conversation surface
- session/model/runtime primitives inherited from DeepSeek Harness
- installable PureGamma capability plugins

Everything domain-specific belongs to a plugin. The existing `apps/web`,
`apps/api`, and Python packages remain as migration sources until a capability
has crossed the compatibility boundary and passed parity tests.

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

## Non-negotiable architecture rules

1. **Harness owns the runtime.** Do not create a second browser Cordis root or a
   second plugin loader inside PureGamma.
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
   add new business functionality to the legacy PG frontend plugin runtime.

## Directory ownership

- `profile/` — the PureGamma DeepSeek Harness profile overlay.
- `plugins/` — target PureGamma Harness plugins and shared service contracts.
- `../apps/web` — legacy/compatibility frontend while migration is in progress.
- `../apps/api` — legacy/compatibility API while migration is in progress.
- `../packages` — existing domain implementations to be wrapped/extracted into
  providers and then retired from direct application ownership.

See `docs/architecture/HARNESS_CORE_V2.md` for the migration map and acceptance
criteria.
