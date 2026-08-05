# Commercial Operations

## Runtime Topology

The production Compose stack runs Web, API, PostgreSQL, Redis, Celery worker,
one scheduler, Nautilus PAPER runtime, and Caddy. PostgreSQL, Redis, API, and
runtime ports remain private to the Compose network. Caddy is the only public
ingress.

Run the iMessage Relay on a separately managed Mac mini. Connect it to the VPS
through WireGuard or another private network and bind the Relay only to that
private interface. Do not run the core API, database, or worker on the Mac.

## Release Sequence

1. Back up PostgreSQL and verify the backup can be read.
2. Run `python scripts/db_migrate.py upgrade`.
3. Run `python scripts/db_migrate.py current` and confirm revision
   `0005_imessage_delivery_retries` or a later reviewed head.
4. Deploy API, worker, scheduler, Web, then Caddy.
5. Confirm `/health` reports both `database: ok` and `redis: ok`.
6. Perform one Stripe test checkout, one portfolio sync, one daily brief, and
   one delivery on every enabled channel.

Only one scheduler replica may run. Due daily briefs and retry deliveries use
database row locks and idempotency keys, but a single scheduler remains the
supported seed-stage topology.

## Monitoring

Every API response includes `X-Request-ID`; use it to correlate reverse-proxy
and application logs. Alert on API health degradation, Celery queue growth,
overdue `failed_retryable` deliveries, Stripe events requiring manual review,
stale data capabilities, and missed daily brief windows.

Logs must not include tokens, Authorization headers, complete message bodies,
verification codes, or Relay secrets.

## Commercial Safety Checks

- Production uses `BILLING_MODE=stripe`, `ENABLE_MOCK_AGENT=false`, and no
  market-data Mock fallback.
- Paid capabilities are enforced by the API, not only hidden in the Web app.
- Subscription recovery uses `subscribed_plan` for billing and `effective_plan` for every execution decision.
- Daily reports and deliveries are idempotent per user/date/channel.
- Failed Agent and notification runs use idempotent refunds.
- iMessage requires Max/Enterprise entitlement, E.164 verification, and a
  private HMAC-authenticated Relay.
- Portfolio connections are read-only and credentials remain server-side.
