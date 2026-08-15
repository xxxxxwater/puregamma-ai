#!/usr/bin/env bash
# Daily ENCRYPTED off-site PostgreSQL backup for LIVE trading operations.
#
#   - dumps postgres inside the compose network
#   - encrypts with gpg (or age) using a passphrase/identity from a file
#   - uploads the encrypted artifact off-site (S3-compatible via aws/rclone)
#   - keeps N local encrypted copies; NEVER writes plaintext backups to disk
#
# Required env (see docs/live-trading/PRODUCTION_DEPLOYMENT.md):
#   PUREGAMMA_ROOT          repo root on the server        (default /puregamma/app)
#   LIVE_BACKUP_DIR         local encrypted backup dir     (default /var/backups/puregamma-encrypted)
#   LIVE_BACKUP_PASSPHRASE_FILE  file containing the encryption passphrase
#   S3_BUCKET               s3://bucket or rclone remote    (required for off-site)
#   LIVE_BACKUP_RETENTION_DAYS  local retention             (default 14)
#
# cron example (root):
#   30 1 * * * /puregamma/app/deploy/live-trading/offsite-encrypted-backup.sh >> /var/log/puregamma-encrypted-backup.log 2>&1
set -Eeuo pipefail

ROOT_DIR="${PUREGAMMA_ROOT:-/puregamma/app}"
BACKUP_DIR="${LIVE_BACKUP_DIR:-/var/backups/puregamma-encrypted}"
PASSPHRASE_FILE="${LIVE_BACKUP_PASSPHRASE_FILE:-/etc/puregamma/backup-passphrase}"
RETENTION_DAYS="${LIVE_BACKUP_RETENTION_DAYS:-14}"
S3_BUCKET="${S3_BUCKET:-}"
S3_ENDPOINT="${S3_ENDPOINT:-}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PLAINTEXT_TMP="$(mktemp)"
ENCRYPTED_BACKUP="${BACKUP_DIR}/postgres-${TIMESTAMP}.dump.gpg"

umask 077
install -d -m 0700 "${BACKUP_DIR}"
trap 'rm -f "${PLAINTEXT_TMP}"' EXIT

cd "${ROOT_DIR}"
docker compose --env-file .env -f docker-compose.production.yml exec -T postgres \
  pg_dump -U puregamma -d puregamma --format=custom --no-owner --no-privileges \
  >"${PLAINTEXT_TMP}"
test -s "${PLAINTEXT_TMP}"

if [[ ! -s "${PASSPHRASE_FILE}" ]]; then
  echo "ERROR: ${PASSPHRASE_FILE} missing; refusing to keep unencrypted backups" >&2
  exit 1
fi

if command -v gpg >/dev/null 2>&1; then
  gpg --batch --yes --pinentry-mode loopback \
    --passphrase-file "${PASSPHRASE_FILE}" \
    --symmetric --cipher-algo AES256 --output "${ENCRYPTED_BACKUP}" "${PLAINTEXT_TMP}"
elif command -v age >/dev/null 2>&1; then
  age -p -o "${ENCRYPTED_BACKUP}" "${PLAINTEXT_TMP}" <"${PASSPHRASE_FILE}"
else
  echo "ERROR: neither gpg nor age is installed" >&2
  exit 1
fi
rm -f "${PLAINTEXT_TMP}"

sha256sum "${ENCRYPTED_BACKUP}" >"${BACKUP_DIR}/checksums-${TIMESTAMP}.sha256"
chmod 0600 "${ENCRYPTED_BACKUP}" "${BACKUP_DIR}/checksums-${TIMESTAMP}.sha256"
find "${BACKUP_DIR}" -type f -mtime "+${RETENTION_DAYS}" -delete

if [[ -n "${S3_BUCKET}" ]]; then
  uploaded=0
  if command -v aws >/dev/null 2>&1; then
    args=(s3 cp --no-progress)
    [[ -n "${S3_ENDPOINT}" ]] && args+=(--endpoint-url "${S3_ENDPOINT}")
    aws "${args[@]}" "${ENCRYPTED_BACKUP}" "${S3_BUCKET%/}/postgres-${TIMESTAMP}.dump.gpg"
    aws "${args[@]}" "${BACKUP_DIR}/checksums-${TIMESTAMP}.sha256" "${S3_BUCKET%/}/checksums-${TIMESTAMP}.sha256"
    uploaded=1
  elif command -v rclone >/dev/null 2>&1; then
    case "${S3_BUCKET}" in
      s3://*) echo "ERROR: rclone needs a configured remote (remote:bucket)" >&2; exit 1 ;;
    esac
    rclone copy "${ENCRYPTED_BACKUP}" "${S3_BUCKET%/}/"
    rclone copy "${BACKUP_DIR}/checksums-${TIMESTAMP}.sha256" "${S3_BUCKET%/}/"
    uploaded=1
  fi
  if [[ "${uploaded}" != 1 ]]; then
    echo "ERROR: no off-site upload client found (aws/rclone)" >&2
    exit 1
  fi
  echo "offsite_encrypted_backup_uploaded ${ENCRYPTED_BACKUP}"
else
  echo "WARNING: S3_BUCKET unset — encrypted backup is LOCAL ONLY; off-site replication is required" >&2
fi

echo "encrypted_backup_ok ${ENCRYPTED_BACKUP}"
