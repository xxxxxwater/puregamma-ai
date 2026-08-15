# Harness Threat Model

Scope: the DeepSeek Harness research layer (runner, orchestrator, Research
Gateway, artifacts) and its interaction with the existing control plane.

## 1. Assets

- User data and conversations (agent history, memory).
- Evidence data and research artifacts.
- Trading accounts, strategies, mandates, orders (highest sensitivity).
- Credits/wallet state.
- Production secrets (`.env`, provider keys, runtime secrets).

## 2. Trust boundaries

| Zone | Components | Trust |
|---|---|---|
| High | API, DB, Redis, Trading Control Plane, Nautilus Runtime | trusted |
| Medium | harness-orchestrator worker, Research Gateway | trusted but least-privilege |
| Low | harness-runner container, Harness SDK subprocess, plugins | **untrusted** |
| External | providers, LLM APIs | untrusted input |

Invariant: the low-trust zone has **no route** to DB, Redis, Docker socket,
Nautilus network, production `.env`, or any long-lived credential. Its only
I/O is the capability-token-gated Research Gateway.

## 3. Threats and mitigations

| Threat | Mitigation |
|---|---|
| Prompt injection drives tool calls | Gateway allowlist (7 tools) is structural; tool names matching denied patterns are rejected before dispatch (`assert_tool_allowed`) |
| Runner escapes container | non-root, `read_only` root fs, `no-new-privileges`, `cap_drop ALL`, no host mounts, resource caps |
| Runner reaches Docker socket / secrets | no socket mount, no `.env` mount, no secret env inheritance (`env_inheritance=()` in Cordis composition) |
| Runner exfiltrates over network | network disabled by default; only `HARNESS_RESEARCH_NETWORK_ENABLED=true` (admin-controlled) can change this |
| Session file persistence abused | writable paths are short-lived tmpfs/ephemeral volumes (`session_root`, `workspace`, `artifact_staging`) destroyed at run end; never host-visible |
| Token reuse / cross-tenant access | one-shot capability tokens bound to run_id + user_id + skill version + allowlist + expiry + call budget |
| Artifact with fabricated citations | server-side validation maps every citation to the frozen EvidenceSnapshot; missing/stale/unauthorized citations force `degraded`/reject |
| Order creation via Harness | no order tool exists in the gateway contract; orders require the existing Trading Control Plane path with confirm/risk gates |
| Kill switch / risk bypass | mandate/kill/risk mutation tools are denied patterns; kill switch is control-plane-only |
| Resource exhaustion / cost | global concurrency 2, per-user 1, per-run timeout + credit budget; budget breach stops the runner and settles actual usage only |
| Supply chain (SDK/plugins) | pinned SDK/runtime versions + Cordis config hash + plugin lock hash recorded per run; no dynamic installs (`pip/npm/npx` forbidden) |
| Event duplication (notifications) | DB outbox with unique idempotency keys; consumers dedupe |

## 4. Explicit non-goals / denied capabilities

Shell, filesystem, editor, URL fetch, browser, arbitrary SQL/GraphQL/RPC,
env/secret reads, Docker, process spawn, orders, strategy/risk/mandate
mutation, kill switch, account connect, withdraw/transfer, payment, direct
messaging. See `packages/harness/security.py` for the enforced lists.

## 5. Residual risks

- An admin-enabled network flag widens exposure: treated as a change
  requiring review; default off.
- The mock adapter is development-only; the real runner must ship with the
  pinned binary and is validated by an isolated manual smoke test only.
- Gateway availability is a hard dependency: fail closed (run degrades)
  when the gateway is unreachable.

## 6. Verification (tests)

`tests/security/test_harness_foundation.py` covers the tool contract, state
machine, tenant isolation, mock determinism and cancel behavior;
`tests/security/test_migration_chain.py` proves a single Alembic head.
Phase 2 adds image-level assertions (no docker.sock, no `.env`, no DB URL,
no Nautilus endpoint, tmpfs-only writable paths).
