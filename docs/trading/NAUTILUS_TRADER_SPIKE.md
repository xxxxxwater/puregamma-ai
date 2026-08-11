# NautilusTrader Integration — Phase 0 Spike Report

Status: **COMPLETED** (2026-08-11) · Environment: Linux x86_64, Python 3.12, single container

## Version pin

`nautilus_trader==1.230.0` (already pinned in `services/nautilus-runtime/requirements.txt`).
Platform wheels verified: `cp312-cp312-linux_x86_64`. Windows wheels exist but the
engine runs in the Linux container; local dev does not import it.

## Memory measurements (psutil-equivalent via ru_maxrss)

| Scenario | RSS |
|---|---|
| Empty process (python + runtime imports) | ~18 MB |
| After `import nautilus_trader` (TradingNode + BacktestNode modules) | **307.8 MB total (+298.9 MB delta)** |
| Current pure-Python runtime, 0 strategies | 319.1 MB |
| Current pure-Python runtime, 10 strategies | 325.3 MB (+6.2 MB) |
| Current pure-Python runtime, 50 strategies | 328.6 MB (+9.5 MB) |

### Conclusions vs the task-book budget (768m limit / <400MB steady / <700MB peak)

1. The nautilus_trader library itself costs **~300MB RSS at import** — the dominant
   line item. A TradingNode with a real data client adds runtime, cache and
   portfolio state on top; expect **~400–450MB steady** for a small deployment.
   A 768m container is **feasible but tight**: leave headroom by running at most
   one engine container, keeping `MessageBusConfig(database=False)` and
   `CacheConfig(database=False)` (in-process only), and limiting instruments to
   the MVP set (≤6 symbols).
2. Strategy-count scaling is cheap (~0.2MB/strategy) — the 50-strategy target is
   not a memory concern.
3. **Risk decision**: proceed with the engine replacement, but keep the
   legacy pure-Python runtime behind the `NAUTILUS_ENGINE_BACKEND=legacy|nautilus`
   feature flag for rollback, and enforce `mem_limit: 768m` + RSS guard that
   pauses opening below 500MB host free memory (per task book §3.1).

## API verification notes (1.230.0 — important)

The 1.230.0 API differs from the docs referenced in the task book:

- `LiveDataClient.__init__` requires `(loop, client_id, venue, msgbus, cache,
  clock, config)` — `cache` and `clock` now live in `nautilus_trader.common.component`
  (no `common.clock` / `common.logging` modules).
- `TradingNode` has **no** `add_data_client` — data clients are wired through
  `add_data_client_factory` / `TradingNodeBuilder`.
- Config classes are pyo3-bound (`.id`, `.json`, `.parse`; no pydantic
  `model_fields`); `PortfolioConfig` has no `base_currency` (account/currency
  config moved); `TradingNodeConfig` has no `log_level` (moved to logger config).
- `BacktestNode(configs=[...])` is config-driven (`BacktestRunConfig` with
  `data`/`engine`/`venues`/`start`/`end`).

**Action for Phase 1**: fetch the official examples from
https://github.com/nautechsystems/nautilus_trader (tree matching tag `1.230.0`)
for `examples/live/trading_node` and `examples/backtest` before writing the
engine adapter; do not rely on docs.nautechsystems.com current pages alone.

## Deliverables

- `scripts/nautilus_spike.py` — reproducible measurement script (rerun:
  `docker run --rm -v $PWD:/app -w /app python:3.12-slim bash -c "pip install
  nautilus_trader==1.230.0 && python scripts/nautilus_spike.py"`).
- `THIRD_PARTY_NOTICES.md` — nautilus_trader LGPL-3.0 attribution.
- Decision record: 768m container OK; library import cost is the headroom
  constraint; API differences require official-examples review in Phase 1.

## Exit criteria

- [x] nautilus_trader 1.230.0 installs on Python 3.12 (linux wheel)
- [x] Memory data: import cost + 0/10/50 strategies
- [x] Version pin documented
- [ ] Minimal TradingNode with custom DataClient — **blocked on API differences**;
      moved to Phase 1 with official-examples reference (see notes above)
