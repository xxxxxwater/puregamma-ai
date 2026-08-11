#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${PUREGAMMA_ROOT:-/opt/puregamma-ai}"
BACKUP_DIR="${PUREGAMMA_BACKUP_DIR:-/var/backups/puregamma}"
RETENTION_DAYS="${PUREGAMMA_BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DATABASE_TMP="${BACKUP_DIR}/postgres-${TIMESTAMP}.dump.tmp"
DATABASE_BACKUP="${BACKUP_DIR}/postgres-${TIMESTAMP}.dump"
RUNTIME_BACKUP="${BACKUP_DIR}/nautilus-runtime-${TIMESTAMP}.tar.gz"

# Off-site upload (S3-compatible). Configure with any S3 client on PATH:
#   S3_BUCKET=s3://puregamma-backups   S3_ENDPOINT=https://... (optional)
# When unset, backups stay local-only and a warning is emitted — off-site
# replication is REQUIRED before relying on backups for recovery.
S3_BUCKET="${S3_BUCKET:-}"
S3_ENDPOINT="${S3_ENDPOINT:-}"

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

if [[ -n "${S3_BUCKET}" ]]; then
  for client in aws rclone s3cmd; do
    if command -v "${client}" >/dev/null 2>&1; then
      case "${client}" in
        aws)
          args=(s3 cp --no-progress)
          [[ -n "${S3_ENDPOINT}" ]] && args+=(--endpoint-url "${S3_ENDPOINT}")
          "${client}" "${args[@]}" "${DATABASE_BACKUP}" "${S3_BUCKET%/}/postgres-${TIMESTAMP}.dump"
          "${client}" "${args[@]}" "${RUNTIME_BACKUP}" "${S3_BUCKET%/}/nautilus-runtime-${TIMESTAMP}.tar.gz"
          "${client}" "${args[@]}" "${BACKUP_DIR}/checksums-${TIMESTAMP}.sha256" "${S3_BUCKET%/}/checksums-${TIMESTAMP}.sha256"
          ;;
        rclone)
          remote="${S3_BUCKET}"
          "${client}" copy "${DATABASE_BACKUP}" "${remote%/}/"
          "${client}" copy "${RUNTIME_BACKUP}" "${remote%/}/"
          "${client}" copy "${BACKUP_DIR}/checksums-${TIMESTAMP}.sha256" "${remote%/}/"
          ;;
        s3cmd)
          "${client}" put "${DATABASE_BACKUP}" "${S3_BUCKET%/}/"
          "${client}" put "${RUNTIME_BACKUP}" "${S3_BUCKET%/}/"
          "${client}" put "${BACKUP_DIR}/checksums-${TIMESTAMP}.sha256" "${S3_BUCKET%/}/"
          ;;
      esac
      echo "offsite_backup_uploaded client=${client} bucket=${S3_BUCKET}"
      break
    fi
  done
  if ! command -v aws >/dev/null 2>&1 && ! command -v rclone >/dev/null 2>&1 && ! command -v s3cmd >/dev/null 2>&1; then
    echo "WARNING: S3_BUCKET is set but no S3 client (aws/rclone/s3cmd) is installed; backup stayed local-only" >&2
  fi
else
  echo "WARNING: S3_BUCKET not set; backup is local-only. Configure off-site replication before relying on it." >&2
fi

printf 'backup_complete timestamp=%s database=%s runtime=%s\n' \
  "${TIMESTAMP}" "${DATABASE_BACKUP}" "${RUNTIME_BACKUP}"
