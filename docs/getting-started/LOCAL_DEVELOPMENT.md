# Local Development
This document describes the development loop for the API, web app, workers, database, and relay.
## Repository Layout
```text
apps/
  api/              FastAPI app and routers
  web/              Next.js app
  imessage-relay/   Self-hosted macOS iMessage relay
packages/
  agents/           Research, market, strategy, risk, sentiment, report writer agents
  data/             Market and sentiment providers
  billing/          Plans, credits, Stripe mapping, entitlements
  notifications/    Email, Telegram, Slack, iMessage providers
  database/         SQLAlchemy models, session, seed data
  workers/          Celery tasks and APScheduler entrypoint
  strategies/       Strategy playbooks
  risk/             Risk scoring helpers
  reports/          Report renderers and templates
```
## API
Install and run:
```bash
python3 -m pip install -r apps/api/requirements.txt
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```
Health:
```bash
curl http://localhost:8000/health
```
API startup calls `ensure_bootstrap()`, which initializes tables and seeds plans, assets, and the demo user.
## Web
```bash
cd apps/web
pnpm install
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm dev
```
The web helper in `apps/web/lib/api.ts` uses fallback data when API calls fail. This is intentional for unfinished backend surfaces.
## Database
Local default in `.env.example`:
```text
DATABASE_URL=postgresql+psycopg://puregamma:puregamma@localhost:5432/puregamma
```
For a lightweight local run without Docker, the app can fall back to SQLite if `DATABASE_URL` is unset because `apps/api/config.py` defaults to `sqlite:///./puregamma.db`.
## Redis and Workers
Start Redis:
```bash
docker compose up -d redis
```
Run Celery:
```bash
celery -A packages.workers.celery_app.celery_app worker --loglevel=info
```
Run scheduler:
```bash
python -m packages.workers.scheduler
```
## iMessage Relay
Use mock mode for normal local development:
```text
IMESSAGE_PROVIDER=mock
```
Run the relay only when testing relay HMAC and idempotency behavior:
```bash
cd apps/imessage-relay
python3 -m pip install -r requirements.txt
export IMESSAGE_RELAY_SECRET=change-me
uvicorn relay:app --host 127.0.0.1 --port 8787
```
On non-macOS systems, the relay can validate requests but returns `unsupported_os` for real sends.
## Tests
```bash
python3 -m pytest
```
Important test areas:
- Auth token creation and protected routes.
- Billing and duplicate Stripe webhook handling.
- Market agent API.
- Notification delivery, idempotency, entitlements, and credit behavior.
## Development Rules
- Do not add real secrets to `.env.example`, docs, tests, or commits.
- Keep investment disclaimers in generated report and signal content.
- Keep live trading disabled for Nautilus-related work.
- Mark mock, placeholder, and planned integrations clearly.
