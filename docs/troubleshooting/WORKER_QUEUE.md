# Worker Queue Troubleshooting

## Symptoms

- Daily reports delayed.
- Notifications not sent.
- Signal scans stale.
- Redis memory high.
- Celery tasks failing.

## Checks

Run worker:

```bash
celery -A packages.workers.celery_app.celery_app worker --loglevel=info
```

Run scheduler:

```bash
python -m packages.workers.scheduler
```

Check Redis:

```bash
redis-cli ping
```

## Common Causes

- Redis unavailable.
- Worker not running.
- Scheduler not running.
- Too many scheduler instances causing duplicate jobs.
- Provider outage causing task failures.
- Database connection failure.

## Mitigation

- Restart worker.
- Restart scheduler after confirming only one instance is active.
- Scale worker count.
- Pause non-critical tasks.
- Re-run daily report generation for affected users.

## Production Improvements

- Add distributed scheduler lock.
- Add retries and dead-letter queues.
- Add queue lag metrics.
- Add per-task timeout and failure alerts.
