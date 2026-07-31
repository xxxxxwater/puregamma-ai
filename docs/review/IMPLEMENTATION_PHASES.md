# Implementation phases

* **P0 Production baseline — code complete, deployment config pending:** startup env validation, Compose/CLI smoke scripts, no production mock/fallback, liveness/readiness, non-root images and local production smoke are implemented. Real secrets, DNS/TLS, backup/restore and target-host topology remain.
* **P1 Metering — implemented:** public Quote/Ledger/Budget/Reward-history APIs; server-only Reservation/Settlement/Refund; append-only ledger and dedicated lifecycle tables; provider usage settlement; automation budgets and rewards.
* **P2 Capability boundary:** registry/status policy and explicit stale/partial/mock UI states.
* **P3 Portfolio fact layer:** connectors, asset master, Decimal NAV, lineage, freshness and reconciliation.
* **P4 Risk Copilot:** deterministic metrics/stress/pre-trade gate; LLM explanation only.
* **P5 Realtime:** Redis Streams, sequence recovery, checkpoints, replay, DLQ and freshness.
* **P6 Global Agent Runtime:** registry, planner, evidence packs and structured artifacts.
* **P7 Trading MCP:** intent journal, one-time challenge, risk gate and runtime reconciliation in PAPER/SHADOW.
* **P8/P9:** restricted testnet, then separately approved restricted live. LIVE/withdrawal/transfer remain disabled by default.
