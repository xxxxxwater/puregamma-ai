#!/usr/bin/env bash
set -Eeuo pipefail
# =========================================================================
# PureGamma AI - Production Deployment Script
# =========================================================================
# This script deploys the entire PureGamma stack (API, Web, DB, Redis, Workers, Caddy)
# including the API Gateway (中转站) infrastructure.
#
# Usage:
#   1. First, copy deploy/production.env to .env and fill in all secrets.
#   2. Run: bash deploy/deploy.sh
# =========================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# -----------------------------------------------------------------
# 0. Pre-flight checks
# -----------------------------------------------------------------
echo "=== Pre-flight checks ==="

if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found. Copy deploy/production.env to .env and fill in all secrets first."
  exit 1
fi

if [ "${APP_ENV:-}" != "production" ] && [ "${APP_ENV:-}" != "prod" ]; then
  echo "NOTE: APP_ENV is not 'production'. This script targets production deployment."
fi

# Validate .env
python3 scripts/validate-production-env.py || {
  echo "WARNING: Environment validation reported issues. Review and fix before deploying."
  echo "Continue anyway? [y/N]"
  read -r answer
  if [ "${answer,,}" != "y" ]; then
    echo "Aborted."
    exit 1
  fi
}

# -----------------------------------------------------------------
# 1. Backup database (if running)
# -----------------------------------------------------------------
echo ""
echo "=== Backing up database ==="
if docker ps --format '{{.Names}}' | grep -q "puregamma-ai-postgres"; then
  echo "Postgres container found. Creating backup..."
  install -d -m 0700 /var/backups/puregamma
  TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  docker exec puregamma-ai-postgres-1 pg_dump -U puregamma -d puregamma --format=custom --no-owner --no-privileges \
    >"/var/backups/puregamma/postgres-${TIMESTAMP}.dump"
  echo "Backup saved to /var/backups/puregamma/postgres-${TIMESTAMP}.dump"
else
  echo "No running Postgres container found. Skipping backup."
fi

# -----------------------------------------------------------------
# 2. Pull latest code (if git repo)
# -----------------------------------------------------------------
echo ""
echo "=== Updating code ==="
if [ -d ".git" ]; then
  git fetch origin 2>/dev/null && echo "Fetched latest from origin." || echo "NOTE: Could not fetch. Using local code."
fi

# -----------------------------------------------------------------
# 3. Build and deploy
# -----------------------------------------------------------------
echo ""
echo "=== Building and deploying ==="
compose_file="docker-compose.production.yml"

# Stop all services first
docker compose --env-file .env -f "${compose_file}" down --remove-orphans 2>/dev/null || true

# Build with no cache for clean images
docker compose --env-file .env -f "${compose_file}" build --no-cache

# Start all services in detached mode
docker compose --env-file .env -f "${compose_file}" up -d

# -----------------------------------------------------------------
# 4. Wait for healthy
# -----------------------------------------------------------------
echo ""
echo "=== Waiting for services to be healthy ==="
attempt=1
max_attempts=30
while [ $attempt -le $max_attempts ]; do
  if docker compose --env-file .env -f "${compose_file}" ps | grep -q "unhealthy\|exited"; then
    echo "WARNING: Some services are unhealthy or exited:"
    docker compose --env-file .env -f "${compose_file}" ps
  fi
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "API is healthy."
    break
  fi
  echo "Waiting for API... ($attempt/$max_attempts)"
  sleep 5
  ((attempt++))
done

if [ $attempt -gt $max_attempts ]; then
  echo "ERROR: API did not become healthy. Check logs: docker compose -f docker-compose.production.yml logs api"
  exit 1
fi

# -----------------------------------------------------------------
# 5. Run migrations
# -----------------------------------------------------------------
echo ""
echo "=== Running database migrations ==="
docker exec puregamma-ai-api-1 python -m scripts.db_migrate upgrade 2>/dev/null || {
  echo "Migration script failed. Check API container logs."
}

# -----------------------------------------------------------------
# 6. Smoke test
# -----------------------------------------------------------------
echo ""
echo "=== Smoke tests ==="
echo "Health check:"
curl -sf http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "Health check failed."
echo ""

# -----------------------------------------------------------------
# 7. Cleanup old images
# -----------------------------------------------------------------
echo ""
echo "=== Cleaning up old images ==="
docker image prune -f --filter "until=24h" 2>/dev/null || true

# -----------------------------------------------------------------
# 8. Status
# -----------------------------------------------------------------
echo ""
echo "=== Deployment complete ==="
echo ""
echo "Services:"
docker compose --env-file .env -f "${compose_file}" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "To view logs: docker compose -f docker-compose.production.yml logs -f"
echo "To check gateway: curl https://api.puregamma.ai/v1/models"
echo ""
echo "=== Next: Gateway Activation ==="
echo "When you have the official provider API keys ready:"
echo "  1. Add keys to .env: GATEWAY_DEEPSEEK_API_KEY, GATEWAY_MOONSHOT_API_KEY, GATEWAY_GLM_API_KEY"
echo "  2. Set GATEWAY_ENABLED=true and add GATEWAY_API_KEY_PEPPER"
echo "  3. Redeploy: docker compose --env-file .env -f docker-compose.production.yml up -d --build api"
echo "  4. Admin bootstrap: POST /admin/gateway/bootstrap then POST /admin/gateway/sync"
echo "  5. Approve pricing: GET /admin/gateway/prices/pending then POST /admin/gateway/prices/{id}/approve"
