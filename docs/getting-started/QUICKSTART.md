# Quickstart
This guide gets a developer running PureGamma AI locally in about 15 minutes with mock billing, mock market data, and mock notifications.
PureGamma AI is research software only. Local reports and signals are demo data and are not financial advice.
## 1. Prerequisites
Install:
- Python 3.11 or newer.
- Node.js 18 or newer.
- `pnpm`.
- Docker Desktop or compatible Docker runtime.
- Optional: Stripe CLI for webhook tests.
## 2. Clone Repo
```bash
git clone <repo-url> puregamma-ai
cd puregamma-ai
```
If you already have the workspace, start from the repository root.
## 3. Copy `.env.example`
```bash
cp .env.example .env
```
Keep these defaults for local mock mode:
```bash
BILLING_MODE=mock
IMESSAGE_PROVIDER=mock
AUTH_ALLOW_DEMO_FALLBACK=false
```
## 4. Run Docker Compose Dependencies
Start Postgres and Redis:
```bash
docker compose up -d postgres redis
```
Check status:
```bash
docker compose ps
```
## 5. Run Backend
```bash
python3 -m pip install -r apps/api/requirements.txt
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```
Check health in another shell:
```bash
curl http://localhost:8000/health
```
Expected:
```json
{"status":"ok","service":"puregamma-api","billing_mode":"mock"}
```
## 6. Run Frontend
```bash
cd apps/web
pnpm install
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm dev
```
Open:
```text
http://localhost:3000/dashboard
```
## 7. Run Worker or Scheduler
For local scheduled jobs:
```bash
python -m packages.workers.scheduler
```
For a Celery worker:
```bash
celery -A packages.workers.celery_app.celery_app worker --loglevel=info
```
The scheduler creates market intelligence, personalized reports, signal scans, daily notifications, and subscription checks.
## 8. Use Mock Login
Create a local demo user and bearer token:
```bash
TOKEN=$(
  curl -s -X POST http://localhost:8000/auth/mock-login \
    -H "Content-Type: application/json" \
    -d '{"email":"demo@puregamma.ai","name":"Demo User"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])'
)
echo "$TOKEN"
```
Use it:
```bash
curl http://localhost:8000/me \
  -H "Authorization: Bearer $TOKEN"
```
## 9. Generate First Report
```bash
curl -X POST http://localhost:8000/reports/daily \
  -H "Authorization: Bearer $TOKEN"
```
List reports:
```bash
curl http://localhost:8000/reports \
  -H "Authorization: Bearer $TOKEN"
```
The daily report costs 10 credits unless a report is already cached for today.
## 10. Send Mock iMessage
iMessage is restricted to Max and Enterprise. In mock billing mode, upgrade the demo user first:
```bash
curl -X POST http://localhost:8000/billing/mock-upgrade \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan_name":"Max"}'
```
Send a mock iMessage notification:
```bash
curl -X POST http://localhost:8000/notifications/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel":"imessage","message":"PureGamma AI test push. ","metadata":{"idempotency_key":"quickstart-imessage-1"}}'
```
The response should contain a `delivery` with `status` set to `sent` and provider response `mode` set to `mock`.
## 11. Run Tests
```bash
python3 -m pytest
```
Optional frontend build:
```bash
cd apps/web
pnpm build
```
## Common Quickstart Problems
| Symptom | Fix |
| --- | --- |
| `Missing bearer token` | Run mock login and pass `Authorization: Bearer $TOKEN`. |
| `Insufficient credits` | Use `POST /billing/mock-upgrade` in mock mode or create a fresh demo user. |
| iMessage delivery skipped | Upgrade to Max in mock mode and ensure the user preference has an iMessage recipient. |
| Frontend shows fallback data | This is expected for Portfolio, Integrations, Data Sources, Daily Push, and Nautilus pages until backend routes are implemented. |
| Postgres connection refused | Run `docker compose up -d postgres redis` and confirm `.env` uses the local `DATABASE_URL`. |
## Next Steps
- Read [Local Development](./LOCAL_DEVELOPMENT.md).
- Read [Mock Mode](./MOCK_MODE.md).
- Configure [Stripe](../integrations/STRIPE.md) in test mode.
- Review [API Reference](../developer/API_REFERENCE.md).
