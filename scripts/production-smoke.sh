#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
"$ROOT/scripts/validate-production-env.py"
if command -v docker >/dev/null 2>&1; then
  docker compose -f docker-compose.production.yml config --quiet
  echo "Production Compose configuration is valid. To start: docker compose -f docker-compose.production.yml up -d --build"
else
  DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
  [ -x "$DOCKER" ] || DOCKER="/usr/local/bin/docker"
  DOCKER_DIR="$(dirname "$DOCKER")"
  PATH="$DOCKER_DIR:$PATH"
  export PATH
  "$DOCKER" compose -f docker-compose.production.yml config --quiet
  echo "Production Compose configuration is valid. To start: $DOCKER compose -f docker-compose.production.yml up -d --build"
fi
