# Harness Research Runbook

Operational guide for the DeepSeek Harness research layer. All flags are
`false` by default; enabling any of them is a reviewed change.

## 1. Feature flags

| Flag | Default | Effect |
|---|---|---|
| `HARNESS_RESEARCH_ENABLED` | false | master switch |
| `HARNESS_RESEARCH_ADMIN_ONLY` | true | only admins may create runs |
| `HARNESS_RESEARCH_NETWORK_ENABLED` | false | runner network access |
| `HARNESS_RESEARCH_ALLOW_CODE` | false | enables `run_research_code` |
| `HARNESS_GLOBAL_CONCURRENCY` | 2 | max concurrent runner jobs |
| `HARNESS_MAX_RUNS_PER_USER_PER_DAY` | 3 | per-user daily cap |
| `HARNESS_RUN_TIMEOUT_SECONDS` | 720 | per-run timeout |
| `HARNESS_RUN_MAX_BUDGET_CREDITS` | 150 | per-run budget ceiling |

## 2. Observability per run

Record and monitor: queue wait, duration, tool count, model tokens,
failure category, artifact validation result, refund status
(`harness_research_runs` + `harness_run_state_transitions`). Agent Chat P95
must stay flat: Harness runs on the dedicated `harness_research` queue and
never competes with the chat worker.

## 3. Common procedures

### Enable deep research (staged)
1. Deploy with `HARNESS_RESEARCH_ENABLED=true`, keep admin-only + no network.
2. Verify queue, states, budget settlement with the mock adapter.
3. Publish the `harness_deep_research` Skill (release_status review →
   published) after admin review.
4. Expand users only after concurrency/budget observations are clean.

### Investigate a stuck run
1. Check `harness_research_runs.status` and latest
   `harness_run_state_transitions`.
2. Stuck beyond `timeout_at`? The orchestrator marks `timed_out` and refunds.
3. Runner logs live in the short-lived tmpfs — check orchestrator logs and
   gateway audit instead.

### Cancel a run
Cancel via the API surface; the orchestrator terminates the runner,
transitions to `canceled`, and refunds the unused reservation (idempotent).

### Budget breach
The orchestrator stops the runner at `max_budget_credits`, settles actual
usage, and records `settlement_status`. Never settle more than quoted.

## 4. Failure and rollback

- Runner failure → `failed` + refund unused reservation.
- Gateway unreachable → fail closed (`failed`, no partial settlement).
- Rollback = disable `HARNESS_RESEARCH_ENABLED`; all tables remain additive
  and no existing automation is affected.

## 5. Alerts (new event types, default off)

`deep_research_completed`, `deep_research_failed`,
`deep_research_requires_review`. They reuse the existing
NotificationDispatcher with unique idempotency keys; retries never duplicate
existing emails/reports.

## 6. Version pinning

`deepseek-harness-sdk`, `runtime-bin`, Cordis config hash and plugin lock
hash are pinned (`packages/harness/versions.py`) and recorded on every run.
Changing any pin requires image rebuild, hash update, and a recorded review.
Dynamic installs (`pip/npm/npx`) are forbidden in the runner image.

## 7. Manual smoke test (isolated environment only)

1. Start compose with flags enabled but network off and mock adapter active.
2. Create one deep-research run as admin; assert
   `queued -> preparing -> running -> validating -> completed`.
3. Assert tool traces ⊆ gateway allowlist; citations map to the frozen
   EvidenceSnapshot.
4. Assert settlement ≤ quoted budget; cancel a second run and assert refund.
5. Assert no order row, no mandate change, no kill-switch change was
   produced by the run.
