# Backup & Restore Runbook

Backups are produced by `scripts/production-backup.sh` (daily via systemd timer,
see `deploy/systemd/`). This document defines the restore procedure, the
recovery drill, and the RPO/RTO contract.

## What is backed up

| Artifact | Path in backup dir | Contents |
|---|---|---|
| Postgres dump | `postgres-<TS>.dump` | Full DB, custom format, `pg_restore` compatible |
| Nautilus runtime state | `nautilus-runtime-<TS>.tar.gz` | `puregamma-ai_nautilus_state` volume (sqlite checkpoints, paper state) |
| Checksums | `checksums-<TS>.sha256` | SHA-256 of both artifacts |

Retention: 7 days local (`PUREGAMMA_BACKUP_RETENTION_DAYS`). **Off-site
replication is mandatory for production**: set `S3_BUCKET` (and optional
`S3_ENDPOINT`) in the deployment environment; the script uploads via
`aws`/`rclone`/`s3cmd` whichever is installed. The script warns loudly when the
backup stays local-only.

## RPO / RTO contract

- **RPO (Recovery Point Objective): 24h** — backups run daily; a disaster loses
  at most the last day of writes. Re-running `production-backup.sh` before
  maintenance narrows this to minutes.
- **RTO (Recovery Time Objective): 2h** — full stack restore from a healthy
  daily backup, following the procedure below, on the same VPS.

## Restore procedure (drill steps)

Prereqs: backup files downloaded to `/var/backups/puregamma/` on the target
host, checksum verified, stack stopped.

```bash
# 0. Verify integrity
cd /var/backups/puregamma
sha256sum -c checksums-<TS>.sha256

# 1. Stop the stack
docker compose --env-file .env -f docker-compose.production.yml down

# 2. Restore Postgres
docker compose --env-file .env -f docker-compose.production.yml up -d postgres
docker compose --env-file .env -f docker-compose.production.yml exec -T postgres \
  sh -c 'exec pg_restore -U puregamma -d puregamma --clean --if-exists' \
  < postgres-<TS>.dump

# 3. Restore Nautilus runtime volume
docker run --rm \
  --volume puregamma-ai_nautilus_state:/target \
  --volume /var/backups/puregamma:/backup:ro \
  alpine:3.22 sh -c 'rm -rf /target/* && tar -C /target -xzf /backup/nautilus-runtime-<TS>.tar.gz'

# 4. Start the rest of the stack
docker compose --env-file .env -f docker-compose.production.yml up -d

# 5. Verify
curl -fsS https://api.puregamma.ai/ready        # database+redis ok
curl -fsS http://localhost:8090/health          # runtime alive
docker compose --env-file .env -f docker-compose.production.yml ps  # all healthy
```

## Quarterly recovery drill (mandatory)

1. Provision a scratch VPS (or reuse staging) with the same compose stack.
2. Copy the newest backup set + `.env` (production secrets) to it.
3. Execute steps 1–5 above.
4. Assert: `/ready` returns 200; one user login works; one report renders; one
   gateway request succeeds; `alembic_version` matches the deployed revision.
5. Record the drill: date, backup timestamp used, restore duration, issues, in
   `docs/ops/drill-log.md`.

## Failure modes

| Symptom | Action |
|---|---|
| `pg_restore` fails on a table | Restore is transactional by table; re-run with `--single-transaction` and report the error |
| Checksum mismatch | Do NOT restore. Use the previous backup set and investigate the bad set |
| Runtime volume empty after restore | The tar was empty; verify source volume name (`docker volume ls \| grep nautilus`) |
| `alembic_version` behind | Run `python -m scripts.db_migrate upgrade` after restore, then re-verify |
