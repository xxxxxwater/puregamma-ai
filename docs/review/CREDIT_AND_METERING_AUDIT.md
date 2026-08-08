# Credits and metering audit
The legacy `packages/billing/credits.py` remains a compatibility price source. The new `packages/billing/metering.py` is the single calculation entry point for dynamic estimates and includes model, token, tool, source, attachment, async and notification dimensions.
Implemented in this baseline:
* `CreditQuote` with model/task bounds;
* reservation through `reserve_task`;
* settlement with multi-refund or extra charge through `settle_task`;
* full refund through `refund_task`;
* persisted `credit_reservations`, `credit_settlements`, `credit_refund_events`, `credit_budget_policies` and `credit_reward_grants`;
* unique idempotency keys at ledger and lifecycle records;
* PostgreSQL/SQLite database triggers plus ORM guards make `CreditLedger` append-only;
* Agent/Luna settle with provider token usage and completed tools; reports, notifications, backtests, signals, strategies, previews and user automations use the same engine;
* automation daily/monthly/per-run hard stops, persisted pause state and next-cost estimates;
* capped/idempotent reward grants with source metadata and audited administrator grants;
* account-to-ledger reconciliation and stale reservation recovery.
API boundary:
* user accessible: `POST /billing/quote`, `GET /billing/ledger`, `GET/PUT /billing/budget`, `GET /billing/rewards`;
* administrator-only: manual reward grant;
* server-only: reservation, settlement, refund, actual token/tool usage and stale-reservation recovery. These must not be exposed to ordinary users.
Operational staging checks still required:
* compare provider invoices against recorded token/tool usage under real OpenAI/DeepSeek accounts;
* alert on `SETTLED_CAPPED`, stale reservation recovery and reconciliation mismatch;
* exercise daily/monthly budget rollover across a real UTC boundary.
