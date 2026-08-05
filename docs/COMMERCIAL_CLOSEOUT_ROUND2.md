# Commercial Closeout Round 2

## Effective Entitlements

Entitlement responses now distinguish `subscribed_plan` from `effective_plan`.
Active and trialing subscriptions receive their purchased capabilities. Past-due
subscriptions retain the purchased-plan reference for billing recovery but use
the Free execution baseline, Email only, no paid daily report, and read-only
access to existing portfolios. Unpaid, expired, canceled, deleted, and inactive
subscriptions use the complete Free baseline without deleting historical data.

Portfolio limits are enforced inside the account creation service. Free and
restricted users cannot add accounts, Pro can add one, and Max can add five.
Existing accounts remain readable and synchronizable after restriction.

Agent document and tool queries enforce the effective data-source entitlement
at execution time. Mentioning X, Bloomberg, on-chain, portfolio, or options in a
prompt cannot bypass the selected and entitled source set.

## Daily Push

The five Daily Push controls now alter the actual delivery body:

- market
- portfolio
- signals
- risk
- source sentiment

Delivery rendering reuses the day's report and database context without a new
LLM call or report Credit charge. Sentiment documents are filtered by the
user's effective data-source entitlement. Message truncation always preserves
the disclaimer.

## Agent Capacity

PostgreSQL user-row and advisory locks remain the seed-stage quota mechanism.
Stale pending/running Agent runs are recovered before quota admission. A real
background priority queue is not present, so non-zero queue priority and the
Max "priority queue" sales claim have been removed. The schema field remains
reserved for a later worker-based Agent execution design.

## iMessage Verification

Verification requires Max/Enterprise entitlement and E.164 normalization.
Requests are limited per user/hour and recipient/day using
`IMESSAGE_VERIFICATION_PER_USER_PER_HOUR` and
`IMESSAGE_VERIFICATION_PER_RECIPIENT_PER_DAY`. A new challenge expires prior
unverified challenges for the same user. Production never returns verification
codes in API responses.

## Database

This closeout changes no database structure. The current reviewed Alembic head
remains `0005_imessage_delivery_retries`; no empty migration was created.

## Verification

Use Python 3.12 and the versions in `apps/api/requirements.txt`:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r apps/api/requirements.txt ruff
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
.venv/bin/ruff check apps packages services tests
```

Validate both frontends independently:

```bash
cd apps/web && npm run typecheck && npm run lint && npm run build
cd apps/site && npm run lint && npm test
```
