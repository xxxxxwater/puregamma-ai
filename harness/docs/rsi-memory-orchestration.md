# PureGamma RSI: bounded recursive orchestration RFC

Status: **implementation in progress**, not a production-unattended or live-trading acceptance. Branch: `refactor/harness-core-v2`. RSI here means *recursive self-improvement of a task plan*, not the market Relative Strength Index. This RFC adds to the existing capability migration; do not regress into mounting old Next.js pages as plugins.

## End state

Keep the permanent UI to PureGamma Harness brand, Harness conversation, and Cordis profile/composition. All finance, automation, data, trading, account, notification, billing, memory and admin surfaces belong to independently installable `@puregamma/dsh-*` plugins, with native Settings/Slots/Resources. The Host owns secrets and business services. Typed Typert Remote provides browser projections. The model proposes plans; deterministic code validates and executes explicitly authorized steps. A plugin never becomes an all-powerful replacement app.

```
Conversation + explicit current user intent
  -> scope and consent gate -> user-approved memory preference projection
  -> Cordis live capability inventory and health -> closed candidate set
  -> TypeSafe Jev optional semantic Choice (server only; no credentials/PII)
  -> deterministic planner / graph / budget / safety / user approvals
  -> host service or official Harness tools (not arbitrary imports)
  -> journal of evidence, usage and outcomes -> verifier -> bounded replan
  -> user-visible result and *proposed* memory improvement (not auto-write)
```

## The capability registry is complete, but availability is not assumed

The 22 contract families are: auth, agent-chat, market-data, data-sources, research, research-runner, secretary, skills, portfolio, portfolio-autopilot, options, backtest, memory, trading, trading-mandates, nautilus-runtime, pg-tsy-runtime, notifications, billing, api-gateway, mobile-api, admin. Each registered action declares `pluginId`, capability, read/write/external/money/live-trade class, typed input and output, health probe, idempotency semantics, authorization scope, approval policy, expected cost, timeout and verifier. Registry declaration != plugin installed or healthy. Missing capabilities are reported as unavailable, never mocked. No wildcard capability grants. Read-only first; add actions only when owners expose explicit safe contracts.

## Memory is evidence, never authority

1. The platform memory service is the sole read and write owner. First fetch its settings: if consent is not explicitly granted or requested scope is disabled, do not fetch or use items. A separate opt-in setting for RSI retrieval and each scope is required before external model disclosure. No cross-user, cross-account, cross-tenant, secret, private credential, medical, account-token, order-credential or unrelated conversation data in Jev requests. Redact and minimize; only user-approved `workflow_preference` fields (`capabilityId`, task preference, provenance, expiry) may influence routing.
2. Memory may rank **already eligible** capabilities and suggest default arguments. It may never modify authorization, grants, risk limit, subscription, API budget, order sizing, venue, recipient, or consent. Treat memory content and retrieved tool output as untrusted data, not instructions. Explicit present-turn user intent overrides a recalled preference; stale or conflicting memory causes clarification or safe read-only fallback.
3. Self-improvement writes are proposals with evidence, version and provenance. User approval, de-duplication, audit and scope retention policy precede persistence. Trading memory remains write-disabled by models. The user can inspect/export/delete memories, opt out and revoke consent; cancellation invalidates in-flight plan snapshots.

## Hard execution policy

Class `read`: read-only, still must be authenticated and scoped. Class `compute`: backtests/research may spend money; require a validated, reserved per-run and daily budget. Class `external`: email, Telegram, iMessage, webhook/test sends and push require explicit user action/recipient verification and permission each relevant scope. Class `account`: billing checkout/cancel/reactivate, API-key management, account deletion and similar mutations require explicit UI or Harness approval and idempotency. Class `trading`: real order entry, amend, cancel, flatten, mandate creation and permission changes require an independently checked trading mandate, venue and instrument scope, current exchange account reconciliation, risk/ownership/lease/fencing gates, explicit human approval and kill switch status. Memories, model confidence, or plugin installation are never authority to trade. Unknown/ambiguous exchange submit stays UNKNOWN; query by client id instead of retrying. Failed integrity -> fail closed, preserve all history.

No plan step executes based on a generated string naming a tool; only registry-backed Host adapters can dispatch after checking current authorization again. Disable side-effectful automatic recursion by default. Explicit execution requires an independently granted session scope. Cancellation aborts effects but does not assume exchange orders were cancelled; reconcile first.

## Bounded RSI loop

`Observe -> propose -> validate -> (approve) -> execute one step -> verify -> checkpoint -> replan`. Enforce maximum depth 3, maximum 8 steps per plan, no cyclic dependencies, strict wall-clock deadline, finite per-run token/currency cap, concurrency ceiling, no retry of an ambiguous side effect, no implicit scope widening. Every proposed improvement gets a new immutable plan version; evaluate against user intent, data provenance, verified outputs and regression tests before promoting it. Persist only approved non-sensitive feedback. Stop on missing data, expired facts, unresolved safety gate, low model confidence, missing budget or missing approval. No background/unattended execution in phase 1.

## TypeSafe/Jev paid call contract

Official HTTP endpoint `POST https://api.typesafe.ai/v1/systemone`, bearer key from server secret `TYPESAFE_API_KEY`, model `jev-latest`, narrow `choice` question over **eligible plugin capability ids plus `none`**. Code constructs options; the model cannot introduce a new capability or permission. Validate `answers.route.type === 'choice'`, chosen id in provided criteria, confidence 0..1, distribution finite; a low-confidence answer becomes review/no-op. Include only a sanitized, minimized task description and capability descriptions in request state. No raw memory/portfolio/order positions/identifiers or auth headers to the model. Errors and rate limits fail closed without blind paid retry. Audit model, request id, outcome, token usage and budget reservation **without** logging key, PII, prompt containing private data, or response internals.

The first live smoke is an explicitly invoked **one-request-only** dry decision: route a synthetic market-research question between `market-data`, `research`, and `none`; no plugin execution, trade, notification or billing mutation. The smoke is NOT a claim of real application end-to-end verification. Use a rotated key placed in server secret manager or an Actions secret, never a key pasted into source, console commands, commits, frontend or CI logs. Billing must reserve budget before any production Jev invocation, settle actual token usage, and fail closed on uncertain accounting. CI uses synthetic fixtures by default; no automatic spend on every push. Until the secret exists safely and a confirmed paid response/usage is recorded, live validation status is BLOCKED.

## Ordered delivery / exit gates

0. Baseline CI green; no production deployment or merge until green.
1. Typed RSI planner/service, capability inventory, opt-in memory projection, safe read-only proposals, zero side effects and policy unit tests.
2. TypeSafe synthetic single paid smoke through secure server-side secret and opt-in gate; quota, billing reserve/settle, idempotent observability and provider failure injection. No money-moving plugin action.
3. Billing UI actions and full lifecycle, Notifications/Daily Push/iMessage UI, pg-tsy runtime read-only, Positions/Orders query and real venue provenance, Trading Safety, Mandates/Approval, Nautilus, Backtest Lab. Keep each plugin separate.
4. Assemble one branded Cordis shell, migrate each of 83 web-page surfaces with redirect/compatibility owners, verify UI and real-user auth. Keep compatibility APIs only while their owners need them.
5. Shadow/staging with live market-data coverage and deterministic safety tests, optional limited user-confirmed canary; only then retire legacy surfaces in documented batches. CI green alone does not imply a safe trading release.

Acceptance tests: consent off prevents memory reads; revoked consent invalidates plan; unrelated or malicious memory cannot issue orders or grant permissions; no installed/healthy adapter -> no action; classifier returns unknown/low confidence -> noop; missing/invalid key -> zero external calls; per-run cap -> zero calls; timeout/429 -> no duplicate paid call; plan cycles/depth/time budget blocked; kill switch and SAFE_HOLD block exposure; ambiguous order never resubmitted; notifications and subscription mutations are approval-gated; user cancellation/restart retains audit. Every integration test must distinguish fixture success, authenticated real paid response, and real venue validation. CI + approved run results are required before PR/merge.