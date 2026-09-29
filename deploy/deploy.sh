#!/usr/bin/env bash
set -Eeuo pipefail

# PureGamma AI production deployment.
# The script is deliberately fail-closed: invalid configuration, stale source,
# failed backup, failed migration, or failed readiness all stop the release.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
COMPOSE=(docker compose --env-file .env -f docker-compose.production.yml)

echo "=== Pre-flight checks ==="
if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found. Copy deploy/production.env to .env and fill in all secrets first."
  exit 1
fi

python3 scripts/validate-production-env.py --env-file .env --require-production
"${COMPOSE[@]}" config --quiet

# Deploy only the canonical clean main checkout when this directory is a git
# worktree. Release bundles without .git remain supported.
if [ -d ".git" ]; then
  branch="$(git branch --show-current)"
  if [ "${branch}" != "main" ]; then
    echo "ERROR: production deploys must run from main (current: ${branch:-detached})."
    exit 1
  fi
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: working tree is dirty; refusing to deploy uncommitted changes."
    exit 1
  fi
  git fetch origin main
  git pull --ff-only origin main
  echo "Deploying main at $(git rev-parse HEAD)"
fi

echo
echo "=== Backing up database ==="
postgres_id="$("${COMPOSE[@]}" ps -q postgres 2>/dev/null || true)"
if [ -n "${postgres_id}" ] && [ "$(docker inspect -f '{{.State.Running}}' "${postgres_id}" 2>/dev/null || true)" = "true" ]; then
  install -d -m 0700 /var/backups/puregamma
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup="/var/backups/puregamma/postgres-${timestamp}.dump"
  docker exec "${postgres_id}" pg_dump -U puregamma -d puregamma --format=custom --no-owner --no-privileges >"${backup}"
  test -s "${backup}"
  echo "Backup saved to ${backup}"
else
  echo "No running PostgreSQL service yet; first deployment has nothing to back up."
fi

echo
echo "=== Building immutable application images ==="
"${COMPOSE[@]}" build --pull

echo
echo "=== Starting stateful dependencies ==="
"${COMPOSE[@]}" up -d postgres redis nautilus-runtime

wait_healthy() {
  local service="$1"
  local attempts="${2:-40}"
  local id
  id="$("${COMPOSE[@]}" ps -q "${service}")"
  if [ -z "${id}" ]; then
    echo "ERROR: service ${service} has no container."
    return 1
  fi
  for ((i=1; i<=attempts; i++)); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${id}")"
    if [ "${status}" = "healthy" ] || [ "${status}" = "running" ]; then
      echo "${service}: ${status}"
      return 0
    fi
    if [ "${status}" = "unhealthy" ] || [ "${status}" = "exited" ] || [ "${status}" = "dead" ]; then
      echo "ERROR: ${service} entered ${status}."
      return 1
    fi
    sleep 3
  done
  echo "ERROR: ${service} did not become healthy."
  return 1
}

wait_healthy postgres
wait_healthy redis
wait_healthy nautilus-runtime

echo
echo "=== Validating application production config inside the built image ==="
"${COMPOSE[@]}" run --rm --no-deps api python -c   'from apps.api.config import Settings, validate_production_settings; validate_production_settings(Settings()); print("application production config valid")'

echo
echo "=== Applying database migrations before API cutover ==="
"${COMPOSE[@]}" run --rm --no-deps api python -m scripts.db_migrate upgrade
"${COMPOSE[@]}" run --rm --no-deps api python -m scripts.db_migrate check

echo
echo "=== Starting application stack ==="
"${COMPOSE[@]}" up -d --remove-orphans api worker scheduler web pocket caddy

wait_healthy api 50
wait_healthy web 50
wait_healthy pocket 50

echo
echo "=== Readiness smoke test ==="
"${COMPOSE[@]}" exec -T api python -c   'import json, urllib.request; data=json.load(urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=5)); assert data.get("status") == "ok", data; print(json.dumps(data, sort_keys=True))'

echo
echo "=== Runtime status ==="
"${COMPOSE[@]}" ps

echo
echo "=== Cleaning dangling images ==="
docker image prune -f --filter "until=24h" >/dev/null 2>&1 || true

echo
echo "=== Deployment complete ==="
if [ -d ".git" ]; then
  echo "Commit: $(git rev-parse HEAD)"
fi
echo "Run deploy/release-final-check.sh for public-route and data-integrity verification."
