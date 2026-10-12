#!/usr/bin/env bash
# Final state check after a release: containers, schema, data integrity and public routes.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [ ! -f ".env" ]; then
  echo "ERROR: .env is required for production final checks."
  exit 1
fi

COMPOSE=(docker compose --env-file .env -f docker-compose.production.yml)
RESEARCH_COMPOSE=(docker compose --env-file .env -f docker-compose.production.yml --profile research-runner)
research_runner_enabled="$(awk -F= '/^RESEARCH_RUNNER_ENABLED=/{print tolower($2); exit}' .env | tr -d '[:space:]')"
research_runner_enabled="${research_runner_enabled:-false}"
SHORT="${1:-}"
if [ -z "${SHORT}" ] && [ -d ".git" ]; then
  SHORT="$(git rev-parse --short=8 HEAD)"
fi

echo "=== containers ==="
"${COMPOSE[@]}" ps
services=(postgres redis nautilus-runtime api worker scheduler web pocket caddy)
if [ "${research_runner_enabled}" = "true" ]; then
  services+=(research-worker)
fi
for service in "${services[@]}"; do
  if [ "${service}" = "research-worker" ]; then
    id="$("${RESEARCH_COMPOSE[@]}" ps -q "${service}")"
  else
    id="$("${COMPOSE[@]}" ps -q "${service}")"
  fi
  if [ -z "${id}" ]; then
    echo "ERROR: missing container for ${service}"
    exit 1
  fi
  state="$(docker inspect -f '{{.State.Status}}' "${id}")"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${id}")"
  if [ "${state}" != "running" ]; then
    echo "ERROR: ${service} is ${state}"
    exit 1
  fi
  if [ "${health}" != "none" ] && [ "${health}" != "healthy" ]; then
    echo "ERROR: ${service} health is ${health}"
    exit 1
  fi
done

if [ -n "${SHORT}" ]; then
  echo "=== image ids for ${SHORT} ==="
  for s in api worker scheduler web; do
    docker image inspect "puregamma-ai-${s}:${SHORT}" --format "${s} {{.Id}}" 2>/dev/null ||       echo "NOTE: immutable tag puregamma-ai-${s}:${SHORT} is not present; compose-managed image is running"
  done
fi

echo "=== schema ==="
"${COMPOSE[@]}" exec -T api python -m scripts.db_migrate check

echo "=== data integrity ==="
data="$("${COMPOSE[@]}" exec -T postgres psql -U puregamma -d puregamma -tAc   "select (select count(*) from users), (select count(*) from agent_conversations), (select count(*) from agent_messages), (select count(*) from agent_attachments), (select count(*) from credit_ledger), (select version_num from alembic_version);")"
echo "${data}"

leftovers="$("${COMPOSE[@]}" exec -T postgres psql -U puregamma -d puregamma -tAc   "select count(*) from users where email like '%@example.invalid';" | tr -d '[:space:]')"
echo "acceptance leftovers: ${leftovers}"
if [ "${leftovers}" != "0" ]; then
  echo "ERROR: acceptance-test users remain in production."
  exit 1
fi

echo "=== internal readiness ==="
"${COMPOSE[@]}" exec -T api python -c   'import json, urllib.request; data=json.load(urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=5)); assert data.get("status") == "ok", data; print(json.dumps(data, sort_keys=True))'

if [ "${research_runner_enabled}" = "true" ]; then
  echo "=== research runner readiness ==="
  "${COMPOSE[@]}" exec -T api python -c 'from apps.api.redis_client import get_redis; value=get_redis().get("pg:research-runner:heartbeat"); assert value, "research heartbeat missing"; print("research heartbeat ok")'
  runner_image="$(awk -F= '/^RESEARCH_RUNNER_IMAGE=/{sub(/^[^=]*=/, ""); print; exit}' .env)"
  runner_image="${runner_image:-puregamma-research-runner:1}"
  docker image inspect "${runner_image}" --format 'research image {{.Id}}' >/dev/null
fi

echo "=== public routes ==="
curl --fail --silent --show-error https://api.puregamma.ai/ready | python3 -m json.tool
curl --fail --silent --show-error --location --max-redirs 3 -o /dev/null https://app.puregamma.ai/zh

# Anonymous protected-route behavior is intentionally reported rather than
# assuming a particular redirect code; authentication policy can evolve.
curl -s -o /dev/null -w 'app /zh/chat anon %{http_code}\n' https://app.puregamma.ai/zh/chat
curl -s -o /dev/null -w 'capabilities anon %{http_code}\n' https://api.puregamma.ai/api/agent/workspace-capabilities

echo "=== served web bundle ==="
chunk="$(curl --fail --silent --show-error https://app.puregamma.ai/zh | grep -o '/_next/static/chunks/[A-Za-z0-9._-]*\.js' | head -1 || true)"
if [ -z "${chunk}" ]; then
  echo "ERROR: no Next.js chunk found on the public app shell."
  exit 1
fi
echo "sampled chunk: ${chunk}"
"${COMPOSE[@]}" exec -T web sh -c "test -d /app/.next-build/static/chunks"
"${COMPOSE[@]}" exec -T web sh -c "grep -rl 'chat-composer-input' /app/.next-build/static/chunks | head -2"

echo "=== api errors in the last 10 minutes ==="
errors="$(docker logs --since 10m "$("${COMPOSE[@]}" ps -q api)" 2>&1 | grep -icE 'traceback|unhandled exception|exception in asgi' || true)"
echo "critical error signatures: ${errors}"
if [ "${errors}" -gt 0 ]; then
  docker logs --since 10m "$("${COMPOSE[@]}" ps -q api)" 2>&1 | grep -iE -C2 'traceback|unhandled exception|exception in asgi' | tail -80 || true
  echo "ERROR: fresh API exception signatures detected."
  exit 1
fi

echo "=== final check passed ==="
