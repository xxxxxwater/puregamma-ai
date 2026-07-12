# Workers and Scheduler

PureGamma AI uses Celery for background tasks and APScheduler for recurring schedules.

## Celery App

Entry point:

```text
packages/workers/celery_app.py
```

Run:

```bash
celery -A packages.workers.celery_app.celery_app worker --loglevel=info
```

Redis is used as both broker and backend through `REDIS_URL`.

## Scheduler

Entry point:

```bash
python -m packages.workers.scheduler
```

Current schedules are UTC:

| Job ID | Trigger | Task |
| --- | --- | --- |
| `shared_daily_market_intelligence` | 00:00 daily | Generate shared market intelligence |
| `personalized_daily_reports` | 00:10 daily | Generate reports for users |
| `market_anomaly_scan` | every 15 min | Scan signals |
| `funding_oi_scan` | every 1 hour | Scan signals |
| `market_regime_summary` | every 4 hours | Refresh market intelligence |
| `send_daily_reports` | 00:20 daily | Send daily report notifications |
| `subscription_status_check` | 01:00 daily | Delegated to Stripe webhooks currently |

## Operational Expectations

- Run exactly one scheduler instance per environment unless using a distributed lock.
- Workers can scale horizontally.
- Add retries, dead-letter queues, and task-level idempotency before production-heavy workloads.
- Preserve notification idempotency keys so duplicate jobs do not send duplicate messages.

## Failure Handling

Current tasks catch some per-user exceptions and continue. For production:

- Log task ID, user ID, source, and failure reason.
- Emit queue lag and failure-rate metrics.
- Retry transient provider failures.
- Stop retrying permanent entitlement and validation failures.
- Alert on queue backlog and repeated daily brief failures.

## Related Runbooks

- [Worker Queue Troubleshooting](../troubleshooting/WORKER_QUEUE.md)
- [Incident Runbook](../admin/INCIDENT_RUNBOOK.md)
