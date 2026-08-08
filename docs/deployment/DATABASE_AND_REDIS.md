# Database and Redis
PureGamma AI stores application state in SQLAlchemy models and uses Redis for Celery broker/backend.
## Database
Current models live in `packages/database/models.py`.
Implemented tables:
- `users`
- `user_preferences`
- `subscriptions`
- `subscription_plans`
- `credit_ledger`
- `stripe_webhook_events`
- `assets`
- `market_snapshots`
- `shared_market_intelligence`
- `signals`
- `reports`
- `alerts`
- `notification_deliveries`
- `backtest_runs`
## Startup Behavior
The API image runs `python -m scripts.db_migrate upgrade` before Uvicorn starts.
Application startup also performs an idempotent `upgrade head` check before seeding
reference data.
- Empty databases are created by Alembic revision `0001_baseline`.
- Existing pre-Alembic databases are stamped only when every current ORM table and
  column is already present. Partial schemas fail closed.
- Production seeds plans, assets, and data-source definitions only. Demo users and
  mock accounts are never created in production.
## Production Requirement
Before rollout:
```bash
python -m scripts.db_migrate check
python -m scripts.db_migrate upgrade
python -m scripts.db_migrate current
```
Create every future schema change with a new Alembic revision. Do not edit the
baseline after it has been deployed and do not restore the former runtime
`create_all`/opportunistic `ALTER TABLE` behavior.
## Backups
Production Postgres should have:
- Automated backups.
- Point-in-time recovery.
- Restore drills.
- Separate credentials for app, migration, and read-only analytics.
- TLS required.
## Redis
Redis is used by Celery:
```text
REDIS_URL=redis://localhost:6379/0
```
Production Redis should have:
- Authentication.
- TLS.
- Memory policy reviewed.
- Queue backlog monitoring.
- Persistence strategy based on task durability requirements.
## Data Retention
Suggested defaults:
- Stripe webhook event audit: retain at least 1 year.
- Notification delivery records: retain at least 1 year or per customer contract.
- Reports and signals: retain per user subscription and data deletion policy.
- Portfolio connector tokens: delete immediately on disconnect.
See [Data Privacy](../security/DATA_PRIVACY.md).
