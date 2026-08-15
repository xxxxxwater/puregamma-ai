# Trading Mandate Runbook

Operational guide for the TradingMandate foundation. Phase 1 ships the data
model, approval and audit path, and PAPER/SHADOW enforcement hooks.
**LIVE automatic trading is not implemented.**

## 1. Feature flags

| Flag | Default | Effect |
|---|---|---|
| `AUTO_TRADING_MANDATES_ENABLED` | false | mandate management surface |
| `AUTO_TRADING_PAPER_ENABLED` | false | paper automatic execution |
| `AUTO_TRADING_SHADOW_ENABLED` | false | shadow signal recording |
| `AUTO_TRADING_LIVE_ENABLED` | false | never effective alone; also requires `AUTO_TRADING_DEPLOYMENT_LIVE_APPROVED=true` and is still refused by policy |

Existing Nautilus guards remain untouched:
`NAUTILUS_LIVE_TRADING_ENABLED=false`, `NAUTILUS_ALLOW_LIVE_ORDER=false`,
`NAUTILUS_ALLOW_WITHDRAWAL=false`, `NAUTILUS_ALLOW_TRANSFER=false`.

## 2. Mandate lifecycle

```
draft (user fills params)
  -> dual confirmation (exact confirmation phrase) + cooldown + expiry
  -> approved (immutable strategy release reference)
  -> execution loop: SignalEvent -> four-layer gate -> PAPER/SHADOW
  -> auto-pause on: stale data, source anomaly, reconciliation required,
     risk breach, consecutive failures, daily-loss breach
  -> resume ONLY via explicit human confirmation
  -> revoke at any time (user or kill switch)
```

## 3. Four-layer gate (fail closed)

Data freshness/integrity → TradingMandate policy → PureGamma pre-trade risk
→ Nautilus independent risk. Any layer failing rejects the action and
writes `trading_mandate_audits` with idempotency key, trace ID, mandate ID,
strategy version, signal ID.

## 4. Shadow fidelity checks

Each Shadow execution records expected price, market touchable price, actual
simulated fill price, slippage, latency, rejection reason, and
reconciliation outcome. Review `shadow_trade_divergence` alerts (default
off) before considering Paper.

## 5. Pause vs kill switch

- Auto-pause is automatic and reversible only by human confirmation.
- Kill switch (`kill_switch_state=active`) has the highest priority, is
  control-plane-only, and Harness can never lift it.

## 6. Recovery procedures

| Symptom | Action |
|---|---|
| Mandate auto-paused | Review audit rows + reason; resume only after explicit human confirmation |
| Reconciliation mismatch | Existing reconciliation flow pauses the mandate; investigate before resume |
| Kill switch active | Stop all mandate execution; do not resume without incident review |
| Unauthorized execution attempt | Fail-closed rejection already recorded; verify audit and alert |

## 7. Rollback

Set `AUTO_TRADING_*` flags to `false` and pause all mandates. Existing
preview/confirm trading flows are unaffected — mandates are additive.

## 8. Never allowed

Harness may never create/approve strategies or mandates, choose capital
sizes, send orders, modify risk limits, lift kill switches, or trigger
orders from its output. Only deterministic `SignalEvent`s may drive the
execution path.
