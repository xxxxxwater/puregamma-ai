# Common Errors

## `Missing bearer token`

Cause: Protected endpoint called without `Authorization: Bearer <token>`.

Fix:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/mock-login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@puregamma.ai","name":"Demo User"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```

## `Invalid bearer token`

Cause: Wrong token, expired token, or changed `JWT_SECRET`.

Fix: Run mock login again.

## `Insufficient credits`

Cause: User does not have enough credits for the action.

Fix in mock mode:

```bash
curl -X POST http://localhost:8000/billing/mock-upgrade \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan_name":"Max"}'
```

## `entitlement_denied`

Cause: Plan does not include requested channel or high-cost task.

Fix: Upgrade plan or use an entitled channel.

## Frontend Shows Mock Data

Cause: Some pages intentionally use fallback data.

Expected for:

- Portfolio.
- Integrations.
- Data Sources.
- Daily Push preferences.
- Nautilus frontend metrics.

## Database Connection Failed

Fix:

```bash
docker compose up -d postgres
```

Confirm `DATABASE_URL` matches host vs container environment.
