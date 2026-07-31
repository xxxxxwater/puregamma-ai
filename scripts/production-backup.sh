#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${PUREGAMMA_ROOT:-/opt/puregamma-ai}"
BACKUP_DIR="${PUREGAMMA_BACKUP_DIR:-/var/backups/puregamma}"
RETENTION_DAYS="${PUREGAMMA_BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DATABASE_TMP="${BACKUP_DIR}/postgres-${TIMESTAMP}.dump.tmp"
DATABASE_BACKUP="${BACKUP_DIR}/postgres-${TIMESTAMP}.dump"
RUNTIME_BACKUP="${BACKUP_DIR}/nautilus-runtime-${TIMESTAMP}.tar.gz"

umask 077
install -d -m 0700 "${BACKUP_DIR}"
cd "${ROOT_DIR}"

compose=(docker compose --env-file .env -f docker-compose.production.yml)
"${compose[@]}" exec -T postgres \
  pg_dump -U puregamma -d puregamma --format=custom --no-owner --no-privileges \
  >"${DATABASE_TMP}"
test -s "${DATABASE_TMP}"
mv "${DATABASE_TMP}" "${DATABASE_BACKUP}"

docker run --rm \
  --volume puregamma-ai_nautilus_state:/source:ro \
  --volume "${BACKUP_DIR}:/backup" \
  alpine:3.22 \
  tar -C /source -czf "/backup/$(basename "${RUNTIME_BACKUP}")" .

sha256sum "${DATABASE_BACKUP}" "${RUNTIME_BACKUP}" >"${BACKUP_DIR}/checksums-${TIMESTAMP}.sha256"
chmod 0600 "${DATABASE_BACKUP}" "${RUNTIME_BACKUP}" "${BACKUP_DIR}/checksums-${TIMESTAMP}.sha256"
find "${BACKUP_DIR}" -type f -mtime "+${RETENTION_DAYS}" -delete

printf 'backup_complete timestamp=%s database=%s runtime=%s\n' \
  "${TIMESTAMP}" "${DATABASE_BACKUP}" "${RUNTIME_BACKUP}"
