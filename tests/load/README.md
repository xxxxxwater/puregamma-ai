# Repeatable load harness

Standalone async scripts (httpx/asyncio) for capacity verification against a
running API. **Never run these against production from a dev box without
explicit approval.** Scripts in this directory are not pytest tests (they are
not collected); the pytest scale smoke lives in `tests/acceptance/` behind
`--runload`.

## Common configuration (env vars, no hardcoding)

| Var | Meaning |
|---|---|
| `PG_LOAD_BASE_URL` | API base URL (default `http://localhost:8000`) |
| `PG_LOAD_TOKEN` | Bearer JWT for authenticated endpoints |
| `PG_LOAD_DATABASE_URL` | DB URL for `digest_fanout.py` verification (defaults to the app settings when run on the server) |

Mint a token on the server (uses the app environment, prints a 24h JWT):

```bash
python - <<'PY'
from apps.api.dependencies import create_access_token
from packages.database.models import User
from packages.database.session import SessionLocal
db = SessionLocal()
print(create_access_token(db.query(User).filter(User.email == "demo@puregamma.ai").one()))
db.close()
PY
```

Or capture the session cookie/JWT from a logged-in browser session.

## Scripts

### `sse_concurrency.py` — N concurrent SSE streams

Opens N concurrent streams (default 50) against
`POST /api/agent/conversations/{id}/messages` (the documented SSE endpoint;
one fresh conversation per stream), measures per-stream time-to-first-event,
prints p50/p95/max vs the 2s acceptance threshold, exits non-zero on
regression.

```bash
# local
python tests/load/sse_concurrency.py --base-url http://localhost:8000 --token <jwt> --streams 50
# staging (env-driven)
PG_LOAD_BASE_URL=https://staging-api.puregamma.ai PG_LOAD_TOKEN=<jwt> \
    python tests/load/sse_concurrency.py --streams 50 --threshold 2.0
# offline validation (no server): in-process app, 3 streams
python tests/load/sse_concurrency.py --self-test --streams 3
```

### `api_latency.py` — non-LLM API latency sampler

Samples `/health`, `/ready` (unauth) and `/api/research/today`, `/portfolio`,
`/reports` (Bearer) round-robin, N=200 requests total at concurrency 20,
reports per-endpoint p50/p95/max vs the 500ms non-LLM p95 target. Exits
non-zero on p95 regression, 5xx, or unexpected 401/403.

```bash
python tests/load/api_latency.py --base-url http://localhost:8000 --token <jwt> \
    --requests 200 --concurrency 20
# offline validation
python tests/load/api_latency.py --self-test --requests 40 --concurrency 8
```

### `digest_fanout.py` — 300-user same-minute digest fan-out

Seeds N demo users (default 300) already due at this minute, triggers
`puregamma.dispatch_due_daily_briefs`, measures completion, then runs
duplicate checks (duplicate `Report` per (user,type,date), duplicate
`NotificationDelivery` idempotency keys, max `failure_count`). Exits non-zero
on duplicates, retries, or failures.

**Requires a running worker + redis** for `--via celery` (the default);
`--via direct` runs the orchestrator in-process (useful on the server with
the app environment). The production orchestrator caps one run at 100 due
preferences, so the trigger loops until a run reports `due == 0`
(expected: ceil(N/100) waves).

```bash
# on the server / staging with app env (worker + redis running):
python tests/load/digest_fanout.py --users 300 --mode db --via celery
# explicit database for the verification queries:
PG_LOAD_DATABASE_URL=postgresql+psycopg://user:pass@host/db \
    python tests/load/digest_fanout.py --mode db --via celery
# no worker available: in-process run (app environment required)
python tests/load/digest_fanout.py --users 60 --mode db --via direct
```

`--mode api` provisions users through the dev-only mock login + preference
PUT; the API never schedules a preference in the past, so those users only
become due at their next local slot — use `--mode db` for the deterministic
same-minute fan-out.

## Targets

| Check | Target |
|---|---|
| SSE time-to-first-event (fast path) | p95 < 2s |
| Non-LLM API latency | p95 < 500ms |
| Digest fan-out | zero duplicate reports/deliveries, `failure_count` ≤ 1 |
