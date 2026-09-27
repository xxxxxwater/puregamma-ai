# Dream-RSI Control Plane

## Purpose

PureGamma's Dream-RSI layer performs **research-only recursive improvement of
the Agent's exploration policy**. It does not retrain the foundation model and
it never grants trading authority.

A user can express a constrained research goal directly in Agent chat:

```text
找一个 BTC 15m，最大回撤 < 12%，Sharpe > 1.8 的策略。
```

The control plane converts that request into a bounded, auditable strategy
discovery run.

## Control-plane flow

```text
Agent Chat goal
      |
      v
DreamGoal
(symbol / timeframe / Sharpe / MaxDD)
      |
      v
Root
├── Momentum
├── VWAP
├── Orderflow
├── Funding + OI
├── Mean Reversion
└── Hybrid
      |
      v
factor variants
      |
      v
parameter variants
      |
      v
causal simulation
      |
      +---- 70% chronological IS
      |
      +---- 30% chronological OOS  <-- constraint metrics
      |
      v
Evaluator
      |
      v
observed Discovery Tree
      |
      v
Replay policies
      |
      v
family compute allocator
      |
      v
next bounded generation
```

The first generation spends one seed evaluation on every family whose required
factors are available. The next generation is not distributed evenly: the
allocator uses observed **OOS** scores, constraint matches, an exploration
floor, and diminishing returns to give stronger families more evaluations
without immediately starving alternatives.

## Strategy families

| Family | Current variants | Required evidence | Quality label |
| --- | --- | --- | --- |
| Momentum | MA cross, breakout | observed OHLC | `observed_close` |
| VWAP | reclaim, deviation trend | OHLC + volume proxy | `rolling_24h_volume_proxy` |
| Orderflow | signed-volume pressure, spread-filtered pressure | OHLC + volume proxy; bid/ask for spread filter | `signed_volume_quote_proxy` |
| Funding + OI | OI trend + funding filter, short-crowding reversal | public perpetual funding and open-interest snapshots | `public_perpetual_snapshot` |
| Mean Reversion | rolling z-score reversion | observed OHLC | `observed_close` |
| Hybrid | momentum+VWAP, momentum+orderflow | combined family factors | `mixed_price_volume_proxy` |

## Data-quality boundary

The current persisted Binance history is a point-quote series rather than a
native trade tape.

- OHLC is aggregated from synchronized observed quote prices.
- VWAP uses an interval estimate derived from rolling 24h volume. It is a
  **VWAP proxy**, not exchange-native bar-volume VWAP.
- Orderflow uses signed price-change × volume pressure and optionally quote
  spread. It is a **proxy**, not L2 imbalance, aggressor-side trades, or a true
  order-flow tape.
- Binance public perpetual funding and open interest are persisted in quote
  provenance when available. Funding+OI is **fail-closed**: if factor coverage
  is below the configured threshold, that family is recorded as
  `factor_unavailable` and receives zero next-generation budget.
- Development mock data may contain synthetic derivatives factors, but the run
  is labeled `development_mock_only` and cannot be presented as verified
  research.

No family silently substitutes a different factor when required data is absent.

## Evaluation semantics

All family signals are causal: the position used for interval N is computed
only from bars known before interval N.

For each bounded candidate:

1. Build the shared requested-timeframe catalog.
2. Keep enough warm-up history for the slowest candidate.
3. Split chronologically: approximately 70% IS / 30% OOS.
4. Compute signal returns with configured fee bps.
5. Annualize Sharpe using `365 * 24 * 60 / timeframe_minutes`.
6. Rank and test the user's Sharpe / MaxDD constraints on **OOS metrics only**.
7. Preserve both IS and OOS metrics in every Discovery Tree node.

Possible statuses are `constraint_satisfied`, `best_effort`,
`timeframe_coverage_insufficient`, `development_mock_only`, and
`no_evaluable_families`.

Backtests remain hypothetical and do not predict future returns.

## Discovery Tree

```text
root
├── family:momentum
│   ├── g0-momentum-...
│   └── g1-momentum-...
├── family:vwap
├── family:orderflow
├── family:funding_oi
├── family:mean_reversion
└── family:hybrid
```

Each experiment node stores family, factor variant, generation, parent,
parameters, factor quality/coverage, IS metrics, OOS metrics, OOS objective
score, and the constraint-match flag.

Each family node stores observations, next-generation budget, best node, best
OOS score, constraint matches, and missing-factor reasons.

## Replay and family compute allocation

Replay never invents an unseen branch outcome. It re-walks only observed nodes
using `observed_order`, `sharpe_first`, `drawdown_first`,
`constraint_first`, and `family_best_first`.

The next-generation policy is
`family_rank_with_exploration_floor_v1`:

- each evaluable family receives one slot when budget permits;
- families rank by observed OOS objective and constraint matches;
- remaining slots use rank-weighted diminishing returns;
- factor-unavailable families receive zero slots;
- candidate generation stays inside the audited bounded family library.

That is the self-improvement boundary: Dream-RSI improves **where the Agent
explores next**, not the execution engine or trading risk policy.

## Agent integration and persistence

`run_dream_strategy_search` is explicitly read-only. Live streams add
`dream.started` and `dream.completed`.

The bounded Dream artifact is persisted in assistant message context before
completion is streamed, so reconnect/reload restores family budgets, metrics
and the Discovery Tree.

The Agent UI shows OOS Sharpe/MaxDD/return, data coverage, best family and
variant, family generation budget, factor quality, and an expandable tree.

## Safety boundary

Dream-RSI cannot create an `OrderIntent`, activate a strategy, change account
or risk limits, enter PAPER/SHADOW automatically, reach LIVE trading, or bypass
existing confirmations and trading mandates.

Candidate promotion into any later PAPER/SHADOW workflow remains a separate
explicit action under the existing control plane.

## Code map

| Area | Location |
| --- | --- |
| Goal parsing, tree, replay, family budget | `packages/dream_rsi/control_plane.py` |
| Family definitions and causal factor logic | `packages/backtest/family_research.py` |
| Shared family sweep | `packages/backtest/engine.py` |
| Timeframe aggregation and factor coverage | `packages/nautilus/data_adapter.py` |
| Binance public funding/OI snapshot persistence | `packages/data/binance_provider.py` |
| Agent routing | `packages/agents/chat/tools.py` |
| Durable Dream events | `apps/api/services/agent_service.py` |
| Dream-RSI result card | `apps/web/components/chat-panels.tsx` |
| Tests | `tests/test_dream_rsi_control_plane.py` |

## Bounded search size

The default goal allows at most 16 evaluated candidates while the family
library contains more candidates than that. Dream-RSI therefore has to choose
where to spend second-generation compute rather than brute-force every variant.

Increasing the limit is a compute-policy change and should be reviewed together
with Agent credits, latency and data quality.
