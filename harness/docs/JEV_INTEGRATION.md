# JEV compatibility and migration gate (2026-09-20)

## Pinned evidence

- Upstream: `vendor/pg-tsy-core-bootstrap` at `0cf5135e0d5159cd8c2fde52af25c3882f24b7c1` (85 commits after the prior pin). Never silently track upstream HEAD at runtime.
- Installed TypeSafe skill is already vendored under `vendor/pg-tsy-core-bootstrap/.agents/skills/typesafe-ai/SKILL.md`; read it before editing a TypeSafe integration, then consult the current official API/primitive docs. Do not re-install duplicate copies.
- Research client: `research/src/pg_tsy/ml/jev_client.py`, server-side `TYPESAFE_API_KEY`, fixed model `jev-1.13.0`, strict `BINANCE_PM:BTCUSDC` and source/expiry checks, bounded timeout, no automatic retry, no order operations.
- Strategy contract: `rust/crates/pg-strategy/src/policy/jev_advisory.rs` exposes a Tokio watch advisory. It can veto an *existing* deterministic new-exposure signal, never manufacture orders, and never block reduce-only due to missing JEV.
- Verification: upstream GitHub Actions run `35493389505` has seven successful jobs including `jev-contract`, `rust-core`, `binance-contract`. This is contract CI, **not** live account or production acceptance.
- `docs/BINANCE_BTCUSDC_ACCEPTANCE_2026-09-18.md` explicitly blocks real/unattended acceptance: the running Rust daemon has no proven end-to-end JEV market-to-strategy bridge, private Binance execution, or durable venue-fill acceptance.

## PureGamma ownership and compatible uses

The existing `@puregamma/dsh-pg-tsy-runtime` service is an operator health boundary, **not** an execution interface. Its read-only `health()/ready()` and approval-disabled `reloadStrategies()` remain separate from strategy signals, positions, orders and mandates. Pinning the new Rust source does **not** update a running daemon or turn on live trading.

1. `pg-tsy-runtime` / Runtime UI: display source, reported health, gating and freshness only. Do not invent JEV readiness from generic `/healthz`, model field strings, or an unverified endpoint. Add a typed read-only JEV telemetry adapter only after the upstream runtime actually exposes a versioned authenticated schema.
2. `research` and `research-runner`: optional, explicitly opted-in TypeSafe/Choice semantic triage over retrieved research evidence; cite inputs, preserve source provenance and abstention, never substitute the model's choice distribution for measured market returns or claim calibrated alpha. LLM routing/intent classification is a separate question schema and requires its own evaluation.
3. `market-data` / `data-sources`: only verified, time-stamped feature snapshots may reach model state. Never pass secrets, raw account identifiers or customer portfolio details to an external model by default; use minimization and consent. Numeric factors, bps, fees, FX, sizing and balance remain deterministic.
4. `trading`, `trading-mandates`, `nautilus-runtime`: JEV observations are advice only. Existing single-owner PolicyEngine -> Risk -> journal -> OMS -> venue route remains authoritative; explicit mandates, lease/fencing, unknown-outcome recovery and reduce-only exits are not model decisions. No JEV-specific order dispatch endpoint or tool.
5. `backtest`: compare deterministic no-JEV baseline with JEV advisor on identical causal samples, record model input+output, event/receive time, TTL, version, fees and p50/p95/p99; never re-query TypeSafe during replay or infer fill priority from public L2.
6. `notifications`: report JEV unavailable, schema drift, stale observations and gating succinctly; alerts are not an excuse to submit replacement orders.

## Release and security invariant

Current status: **source synchronization + interface mapping only**. Do not enable live JEV, claim profitability or merge solely because contract tests are green. API credentials live only in operator-controlled server secrets (`TYPESAFE_API_KEY`); never embed a real key in repo, profile YAML, frontend, telemetry, fixture or CI. Rotate any key shared in chat before use. Cloud inference must be bounded/coalesced and off the execution/cancel/exit hot path. Fail JEV-dependent new entries closed while preserving safe exits. A real bridge needs independent schema tests, time-aligned replay, fault injection and a separately authorized canary; do not touch the incumbent Freqtrade PM bot or manually owned positions.
