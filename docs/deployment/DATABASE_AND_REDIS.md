# Database and Redis

PureGamma.ai stores application state in SQLAlchemy models and uses Redis for Celery broker/backend.

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

`apps/api/dependencies.py` calls `ensure_bootstrap()` on startup. It runs:

- `init_db()`, which calls `Base.metadata.create_all`.
- `seed_all()`, which seeds plans, assets, and demo user data.

## Production Requirement

Add a migration tool such as Alembic before production schema changes. `create_all` is acceptable for local MVP work but not enough for controlled production migrations.

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
