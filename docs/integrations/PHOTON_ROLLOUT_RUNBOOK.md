# Photon iMessage — Rollout Runbook

Scope of this release: the Cordis frontend plugin runtime and the Photon
provider/inbound pipeline ship in the same version, but Photon is NOT
enabled at first deploy. The launch default stays
`IMESSAGE_PROVIDER=disabled` (or `macos_relay` where the relay is already
operational). Photon is never an automatic fallback for the Mac relay.

## 1. What shipped (this version)

- Photon outbound provider (`packages/notifications/imessage/photon_provider.py`):
  text + media via the Advanced HTTP Proxy, bearer token, `Idempotency-Key`,
  bounded retries, safe response sanitization.
- Photon inbound pipeline (P0):
  `POST /internal/imessage/photon/webhook` verifies the X-Spectrum
  signature (`v0:{timestamp}:{rawBody}` HMAC-SHA256, 5-minute replay
  window), the event/line/direction/platform/content filters, persists a
  `photon_inbound_tasks` row (idempotent on Photon message.id) and enqueues
  a Celery task before returning 2xx.
  The worker (`puregamma.process_photon_inbound`) runs the SHARED agent
  flow and sends the reply through `PhotonIMessageProvider` with
  idempotency key `photon-inbound-reply:{message_id}`; replies are audited
  in `notification_deliveries` WITHOUT the user-notification billing path.
  Failures retry up to 3 attempts (1/5/30 min) then go `failed_permanent`;
  a per-minute reaper recovers crashed/stuck rows.
- Database migration `0029_photon_inbound_tasks` (new head).
- Cordis frontend runtime: builtin-whitelist-only plugin loading driven by
  `GET /api/frontend/plugins`; client-only Context; no third-party plugins.

## 2. Release defaults (no Photon cutover)

First deploy ships with:

```env
IMESSAGE_PROVIDER=disabled   # or macos_relay where the relay is live
```

Cordis and the Photon code are present but inert: the webhook is never
registered upstream, the worker marks any stray task
`failed_permanent/photon_provider_disabled`, and production config
validation passes with either provider.

## 3. Pre-deploy checklist

1. Database backup (pg_dump) + image tags carrying the commit SHA.
2. `python3 scripts/validate-production-env.py` with the real `.env`
   (redacted output; must print "Production environment valid").
3. `docker compose --env-file .env -f docker-compose.production.yml config --quiet`
   on the deployment host.
4. On Linux: `docker compose --env-file .env -f docker-compose.production.yml build`.
   (Windows cannot run the standalone-copy step: symlink EPERM; build on the
   Linux deploy host / CI instead.)
5. `python3 scripts/db_migrate.py upgrade` before switching traffic.

## 4. Staging smoke (before ANY production cutover)

With `IMESSAGE_PROVIDER=photon` on STAGING only and all five PHOTON_* vars set:

1. Register the webhook at `https://api.<staging-domain>/internal/imessage/photon/webhook`.
2. Isolated test number: request an iMessage verification code -> delivered?
3. Send an outbound text (notification send) -> delivered?
4. Send an inbound text -> agent reply arrives within the worker SLA.
5. Re-deliver the same webhook -> exactly one reply (idempotency).
6. Wrong-signature / expired-timestamp webhooks -> 401 (Photon stops retrying).
7. Attachment webhook -> 2xx `unprocessed`; no crash.
8. Mac relay regression when staging still has `macos_relay`:
   `POST /internal/imessage/inbound` behaves exactly as before.

Only after ALL smoke items pass may the production `.env` switch to photon.

## 5. Production switch (only after staging smoke)

```bash
# 1. Backup + migrate
docker compose --env-file .env -f docker-compose.production.yml stop api worker
python3 scripts/db_migrate.py upgrade
# 2. Edit .env:
#    IMESSAGE_PROVIDER=photon
#    PHOTON_API_KEY=...      PHOTON_LINE_ID=...   PHOTON_SERVER_URL=...
#    PHOTON_HTTP_PROXY_URL=...  PHOTON_WEBHOOK_SECRET=...
# 3. Deploy the tagged image, then register the webhook upstream.
# 4. Verify:
curl -fsS https://api.<domain>/ready
curl -fsS -H "Authorization: Bearer $TOKEN" https://api.<domain>/api/frontend/plugins
docker compose --env-file .env -f docker-compose.production.yml ps  # worker running
# Celery queue draining: no photon_inbound_tasks stuck in pending/processing
# beyond the reaper window (1 min).
```

## 6. Rollback (explicit, non-destructive)

```bash
# Restore the previous image tag, then in .env:
IMESSAGE_PROVIDER=disabled   # or macos_relay with IMESSAGE_RELAY_SECRET
docker compose --env-file .env -f docker-compose.production.yml up -d
# Unregister the Photon webhook upstream.
```

- NEVER delete database volumes (`pgdata`, `redisdata`) during rollback.
- Pending `photon_inbound_tasks` rows are archived as
  `failed_permanent/photon_provider_disabled` by the worker; re-enabling
  photon later does NOT resurrect replies from the disabled window (by
  design — those messages must be handled manually).
- Migration 0029 is forward-only in practice: `downgrade()` drops the task
  table, so only run it if Photon is permanently abandoned and rows are
  archived/exported first.

## 7. Known limitations (documented, not hidden)

- Inbound media attachments are acknowledged (`unprocessed`) but NOT
  processed: the webhook carries no attachment bytes. Media inbound needs
  the Photon SDK/Proxy attachment download capability (future phase).
- If the Photon proxy ignores the `Idempotency-Key` header, the local
  `notification_deliveries` unique key is the trusted dedup boundary.
- Cordis is currently the builtin-plugin infrastructure; page data flows
  are not yet migrated to plugin panels (opt-in via `PluginPanelSlot`).
