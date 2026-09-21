# PureGamma Harness integration and release gates

Snapshot: 2026-09-21. This is a **blocker ledger**, not a production acceptance certificate. The authoritative result for each check must reference the exact final merge commit and deployed image digest. Do not change production based on this document alone.

## 0. Source-of-truth and branch synchronization — BLOCKED

- Proposed source: `refactor/harness-core-v2`; integration target: `main`. On 2026-09-21, the branches diverged at `185802e602272b8eaca277512f0ede113e5f02d3`. Main had 61 additional commits, the refactor 17. No integrated CI has been run.
- Preserve all main-only work before merging, particularly the September 21 production PM NAV configuration/allowlist fixes; JEV read-only advisory route and UI; pocket authentication/relay; trading/portfolio routes; migrations through Alembic 0032; service deployment/rollback files; tests and latest Rust submodule revision. Do not overwrite or discard newer main code to silence conflicts.
- Resolve `vendor/pg-tsy-core-bootstrap` pin explicitly: this branch pins `0cf5135`, while main advanced to `f5a6382` (main commit `78daf726`). Verify both vendored source revisions and update the CI pin on the actual integration branch. Pinning a submodule does not build, test or deploy the Rust daemon.
- Rebase/merge with a clean worktree and a reviewed conflict log, then rerun *all* required CI, Python tests, Rust tests, browser E2E and security checks **against the actual resulting tree**. The branch-only green run `35557633934` is not evidence for the merged code.

## 1. Harness architecture / product parity — BLOCKED

- Shell must remain conversation-first, showing only PureGamma Harness brand + conversation + Cordis profile/composition. No second root Context, legacy page bundle wrapped as a plugin, direct old-API fetch in browser UI plugins, or independently maintained Redux-style duplicate remote state.
- Domain ownership is granular: Billing and explicit subscription actions; Notifications / Daily Push / iMessage (including verified recipient and delivery history); PG-TSY health and events; portfolio positions and orders; Trading Safety; independently granted Mandates/Approval; Nautilus lifecycle; Backtest Lab + streaming/export; account/security; rest of the 83 tracked web surfaces. A migration ledger is not parity proof.
- For each old route/page, record old → owner plugin, read/write permissions, server identity binding, expected observable states (loading, unavailable, stale, errors), bilingual UI, lifecycle cleanup, streaming/binary semantics, and successful end-to-end evidence. Retire old pages only after route-by-route parity and rollback are verified.
- Verify Google/Apple/email authentication, per-user authorization for Host Remotes and paid actions, billing webhook/session idempotency, Stripe checkout/portal/cancellation and credit ledger, iMessage verification rate limits, notification send/delivery idempotency, and role separation. A fixed server-side bearer token is not by itself proof of end-user authorization.
- No simulated NAV, zero balance, healthy process, order, price, signal or live eligibility may be invented when provider data is unavailable. Show source, timestamp, freshness and error states.

## 2. Trading permission boundary — BLOCKED

- `harness/plugins/trading` and `harness/plugins/trading-mandates` currently define abstract services and policy contracts. A contract, UI resource or successful typecheck does not imply an installed persistent execution provider, durable one-use reservation or live readiness. Installing the PG-TSY UI plugin must not enable execution; strategy reload stays disabled in the default profile.
- Distinguish production's existing **Python Binance Spot** gateway and control plane (`packages/live_trading/`) from a future native Harness `TradingService` adapter and the independent Rust PG-TSY runtime. Do not claim the former automatically implements the latter or supports Binance Portfolio Margin, Hyperliquid or IBKR. Adapter scope, permissions, order types and account types need separately signed acceptance.
- To implement a real provider, enforce authenticated requester and server-owned mandate/approval/risk evidence, a durable one-time approval+reservation transaction keyed by `clientOrderId` and exact intent hash, position ownership and independent kill-switch/fencing. Model-proposed signals cannot approve themselves or cause unreviewed order submission.
- The submit-timeout state is UNKNOWN; recover by client order ID and exchange reconciliation, **never blind retry**. Keep cancel, query, fill ingestion and reconciliation functional under a kill switch; validate reduce-only in pre-trade, venue mapping and post-trade accounting.

## 3. Required test evidence before live deployment — BLOCKED

1. On integrated and pinned code, Rust toolchain `cargo build` / unit/integration tests plus Python/FastAPI migrations and tests, all with exact SHA, toolchain and logs. Include schema migration dry-run, restore and unchanged historical ledgers.
2. Shadow/staging against real exchange read-only order, position and fill endpoints. Prove signed auth, client-order-id lookup after terminal fills, journal/venue reconciliation, missing-stop fail-closed, partial fill, cancel storm, rate-limit budget, WS disconnect/resync, lease expiry, restart recovery and network timeout/UNKNOWN.
3. Testnet order → exchange acknowledgment → fill and fee → immutable ledger → NAV → reconciliation, with matching IDs and timestamps. Demonstrate no duplicate orders under POST-then-crash, retries and cross-process fencing. Confirm no exposure increase for reduce-only and no bypass by stale approval.
4. Production operator must review permissions/withdrawal disabled, risk limits, real account ownership, rollback and emergency-stop ability. Perform a *separately authorized* small-canary first order per `docs/live-trading/FIRST_ORDER_VERIFICATION.md` on current main. Capture redacted evidence and signoff; block if any section fails.
5. Observe a sustained soak of runtime health, feed freshness, broker order history, journal, alert delivery, risk gates, and memory/disk. Validate container image digest, backup and rollback. No blanket ‘unattended/live ready’ conclusion without these results.

## 4. Distinct release decisions

- **Mergeable:** conflict-free integration onto current `main`, all resulting-tree CI and parity/security test gates green, reviewed diff and rollback. A green source-branch job alone is insufficient.
- **UI production cutover:** independently validated login, billing, notification, portfolio and research parity, deployed host/remote routing, feature flags and rollback. Existing production APIs/pages remain until replaced. Do not change the Python execution path as a side effect of UI cutover.
- **Live trading:** all section 3 evidence, signed mandate/approval and operator authorization. Default stays disabled, trading provider absent or gated. CI/build success is never live permission.

## 5. Evidence register (update only with real results)

| Evidence | Status | Pointer |
| --- | --- | --- |
| Refactor branch CI | PASS (branch only) | Actions run `35557633934`, HEAD `de56547f` |
| Integrated current-main CI | NOT RUN | — |
| Main-only feature / migration conflict resolution | NOT VERIFIED | — |
| Latest PG-TSY Rust build + tests | NOT VERIFIED | — |
| UI route-by-route parity + browser E2E | NOT VERIFIED | — |
| End-user Host Remote authorization + approval persistence | NOT VERIFIED | — |
| Testnet / shadow / restart fault-injection | NOT VERIFIED | — |
| Signed canary and production rollback rehearsal | NOT VERIFIED | — |

All unchecked entries are release blockers. Do not convert NOT VERIFIED to PASS based on intention, a source comment or an abstract interface.
