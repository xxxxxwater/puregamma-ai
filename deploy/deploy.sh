#!/usr/bin/env bash
set -Eeuo pipefail

# PureGamma AI production deployment.
# The script is deliberately fail-closed: invalid configuration, stale source,
# failed backup, failed migration, or failed readiness all stop the release.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
COMPOSE=(docker compose --env-file .env -f docker-compose.production.yml)
RESEARCH_COMPOSE=(docker compose --env-file .env -f docker-compose.production.yml --profile research-runner)

echo "=== Pre-flight checks ==="
if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found. Copy deploy/production.env to .env and fill in all secrets first."
  exit 1
fi

research_runner_enabled="$(awk -F= '/^RESEARCH_RUNNER_ENABLED=/{print tolower($2); exit}' .env | tr -d '[:space:]')"
research_runner_enabled="${research_runner_enabled:-false}"

python3 scripts/validate-production-env.py --env-file .env --require-production
if [ "${research_runner_enabled}" = "true" ]; then
  "${RESEARCH_COMPOSE[@]}" config --quiet
else
  "${COMPOSE[@]}" config --quiet
fi

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
if [ "${research_runner_enabled}" = "true" ]; then
  "${RESEARCH_COMPOSE[@]}" build --pull research-worker
  runner_image="$(awk -F= '/^RESEARCH_RUNNER_IMAGE=/{sub(/^[^=]*=/, ""); print; exit}' .env)"
  runner_image="${runner_image:-puregamma-research-runner:1}"
  echo "Building isolated research image: ${runner_image}"
  docker build --pull -f packages/research_runner/Dockerfile.runner -t "${runner_image}" .
fi

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

if [ "${research_runner_enabled}" = "true" ]; then
  echo
  echo "=== Starting isolated research worker ==="
  "${RESEARCH_COMPOSE[@]}" up -d research-worker
  wait_healthy research-worker 40

  echo "=== Waiting for research worker heartbeat ==="
  heartbeat_ok=false
  for ((i=1; i<=20; i++)); do
    if "${COMPOSE[@]}" exec -T api python -c 'from apps.api.redis_client import get_redis; raise SystemExit(0 if get_redis().get("pg:research-runner:heartbeat") else 1)' >/dev/null 2>&1; then
      heartbeat_ok=true
      break
    fi
    sleep 3
  done
  if [ "${heartbeat_ok}" != "true" ]; then
    echo "ERROR: research worker failed to publish a readiness heartbeat."
    exit 1
  fi
  echo "research-worker: heartbeat ok"
fi

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
