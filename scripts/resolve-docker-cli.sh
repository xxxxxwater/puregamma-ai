#!/usr/bin/env sh
set -eu

if command -v docker >/dev/null 2>&1; then
  DOCKER="$(command -v docker)"
elif [ -x "/Applications/Docker.app/Contents/Resources/bin/docker" ]; then
  DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
elif [ -x "/usr/local/bin/docker" ]; then
  DOCKER="/usr/local/bin/docker"
else
  echo "Docker CLI not found; install Docker Engine/Desktop." >&2
  exit 1
fi

if "$DOCKER" compose version >/dev/null 2>&1; then
  echo "$DOCKER compose"
elif command -v docker-compose >/dev/null 2>&1; then
  echo "$(command -v docker-compose)"
else
  echo "Docker Compose not found for $DOCKER" >&2
  exit 1
fi
