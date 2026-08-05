# Incident Runbook

Use this runbook for operational incidents. Preserve user trust: communicate clearly, avoid investment advice, and state when data is partial or stale.

## 1. Stripe Webhook Failure

Symptoms:

- Checkout succeeds but plan does not update.
- Credits not granted.
- `/admin/stripe-events` shows missing or unprocessed events.

Dashboard to check:

- Stripe dashboard events.
- Admin Stripe events page.
- Billing/subscription page.

Logs to check:

- API logs for `/stripe/webhook`.
- Stripe signature verification errors.
- Database errors on `stripe_webhook_events`.

Immediate mitigation:

- Verify `STRIPE_WEBHOOK_SECRET`.
- Replay failed event from Stripe dashboard.
- Keep duplicate event protection intact.

User communication:

- "Your payment completed, but account activation is delayed. We are reconciling billing state."

Long-term fix:

- Add webhook failure alerting, replay tooling, and credit reconciliation job.

## 2. iMessage Relay Offline

Symptoms:

- iMessage deliveries fail.
- Relay `/health` unreachable.
- Provider response contains connection errors.

Dashboard to check:

- Admin notification deliveries.
- Relay host process monitor.

Logs to check:

- API notification logs.
- Relay logs.
- LaunchAgent logs on Mac.

Immediate mitigation:

- Restart relay.
- Switch affected users to email/Telegram if configured.
- Mark iMessage source degraded.

User communication:

- "iMessage delivery is delayed. Your report remains available in the web app and alternate channels may still work."

Long-term fix:

- Add relay uptime monitoring, auto-restart, and deterministic retry queue.

## 3. Worker Queue Backlog

Symptoms:

- Daily reports not generated on time.
- Queue latency rising.
- Signals stale.

Dashboard to check:

- Worker queue dashboard.
- API report counts.
- Data freshness dashboard.

Logs to check:

- Celery worker logs.
- Scheduler logs.
- Redis metrics.

Immediate mitigation:

- Scale workers.
- Pause non-critical scans.
- Run daily report task manually for affected users.

User communication:

- "Daily research generation is delayed. Existing reports remain available."

Long-term fix:

- Add queue lag alerts, task priorities, retries, and dead-letter queues.

## 4. Plaid Sync Outage

Symptoms:

- Brokerage holdings stale.
- Link or sync errors.
- Portfolio NAV shows partial data.

Dashboard to check:

- Portfolio source health.
- Plaid dashboard.
- User integration status.

Logs to check:

- Plaid API errors.
- Token exchange logs.
- Portfolio sync worker logs.

Immediate mitigation:

- Mark Plaid source stale.
- Keep NAV visible with `partial_data=true`.
- Stop automatic conclusions based on missing brokerage data.

User communication:

- "Brokerage sync is delayed. Portfolio NAV may be partial until Plaid connectivity recovers."

Long-term fix:

- Add re-auth flow, source-level SLA, and stale-source alerts.

## 5. X API Rate Limit

Symptoms:

- X KOL source stale.
- Sentiment scan failures.
- Admin data source status shows rate limit.

Dashboard to check:

- Data source monitoring.
- Provider usage dashboard.

Logs to check:

- X provider responses.
- Worker task failures.

Immediate mitigation:

- Reduce scan frequency.
- Mark X source stale.
- Remove X-dependent claims from daily brief until fresh.

User communication:

- "KOL sentiment is temporarily stale. Market and portfolio sections remain available."

Long-term fix:

- Add budgeted polling, caching, and KOL priority tiers.

## 6. LLM Provider Failure

Symptoms:

- Report generation errors.
- Slow or empty LLM completions.
- Fallback text appears.

Dashboard to check:

- LLM usage dashboard.
- Report generation dashboard.

Logs to check:

- LLM client errors.
- Timeout and rate-limit logs.

Immediate mitigation:

- Use mock or template fallback.
- Disable high-cost generation if quality is degraded.
- Retry with lower concurrency.

User communication:

- "AI report generation is degraded. We are using fallback summaries where available."

Long-term fix:

- Add provider fallback, budget controls, and prompt/version observability.

## 7. Portfolio NAV Incorrect

Symptoms:

- User reports wrong NAV.
- Large unexplained NAV move.
- Missing or stale positions.

Dashboard to check:

- Portfolio source health.
- Account sync status.
- Price source freshness.

Logs to check:

- Plaid/exchange/wallet sync logs.
- Price selection logs.
- NAV calculation logs.

Immediate mitigation:

- Mark NAV partial or stale.
- Disable affected source from NAV if clearly bad.
- Re-run sync after fixing source.

User communication:

- "Portfolio NAV is being reviewed and may be inaccurate. It should not be treated as an official statement."

Long-term fix:

- Add reconciliation tools, per-position source trace, and anomaly detection.

## 8. Data Source Stale

Symptoms:

- Source freshness exceeds SLA.
- Reports show old timestamps.
- Admin data source stale warning.

Dashboard to check:

- Data source monitoring.
- Worker dashboard.

Logs to check:

- Provider fetch logs.
- Cache logs.
- Worker task logs.

Immediate mitigation:

- Mark source stale.
- Continue with partial data if safe.
- Suppress source-specific claims.

User communication:

- "One or more data sources are stale. Reports may omit or label affected sections."

Long-term fix:

- Add source SLAs, backoff, alternate providers, and freshness gates in report writer.

## 9. Duplicate Notifications

Symptoms:

- User receives duplicate email, Slack, Telegram, or iMessage messages.
- Multiple deliveries with similar payloads.

Dashboard to check:

- Admin notification deliveries.
- Worker schedule runs.

Logs to check:

- Notification idempotency keys.
- Scheduler duplicate instances.
- Relay SQLite delivery records for iMessage.

Immediate mitigation:

- Stop duplicate scheduler instance.
- Use deterministic idempotency keys.
- Pause affected channel if needed.

User communication:

- "Some users may have received duplicate notifications. No action is required."

Long-term fix:

- Add distributed scheduler lock and duplicate-send alerting.

## 10. Suspected Secret Leak

Symptoms:

- Secret appears in logs, ticket, screenshot, or repository.
- Provider reports suspicious usage.
- Unexpected API calls or billing usage.

Dashboard to check:

- Secret manager audit logs.
- Provider dashboards.
- API logs.

Logs to check:

- Git history.
- CI logs.
- App logs for leaked value patterns.

Immediate mitigation:

- Revoke or rotate the secret.
- Disable affected integration.
- Remove exposed artifacts where possible.

User communication:

- Communicate only verified impact and required user action.

Long-term fix:

- Add secret scanning, log scrubbing, least-privilege keys, and rotation drills.

## 11. User Data Deletion Request

Symptoms:

- User requests deletion.
- Enterprise customer invokes data rights process.

Dashboard to check:

- User record.
- Connector status.
- Reports, notifications, credit ledger, and billing links.

Logs to check:

- Support ticket.
- Admin access logs.
- Connector deletion logs.

Immediate mitigation:

- Verify requester identity.
- Disconnect Plaid/exchange/wallet integrations.
- Delete or anonymize user data according to policy and legal requirements.
- Preserve records that must be retained for billing/legal audit.

User communication:

- "We have received your deletion request and will process it according to our retention obligations."

Long-term fix:

- Build self-service deletion workflow, export, audit trail, and retention automation.
