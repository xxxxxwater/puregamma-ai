#!/usr/bin/env bash
# Roll back the four PureGamma application services to a recorded image pin.
#
# Usage:
#   bash /puregamma/release-rollback.sh /puregamma/override-<stamp>-before-<short>.yml
#
# Database migrations are intentionally NOT downgraded. PureGamma migrations are
# forward-only in production; operators must only select a code pin documented as
# compatible with the current schema. This script verifies runtime health, not
# historical schema compatibility.
set -Eeuo pipefail

PIN="${1:?usage: release-rollback.sh /puregamma/override-<stamp>-before-<short>.yml}"
[ -f "$PIN" ] || { echo "ERROR: pin file $PIN not found"; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LIVE_BUILD="/puregamma/app"

# Prefer an explicitly selected target context. Otherwise use the build named
# by the target pin, then the newest complete immutable build.
BUILD="${BUILD_DIR:-}"
if [ -z "$BUILD" ]; then
  named="$(basename "$PIN" | sed -n 's/.*-\([0-9a-f]\{7,40\}\)\.yml$/\1/p')"
  for candidate in "/puregamma/build-$named" /puregamma/build-*; do
    [ -f "$candidate/docker-compose.production.yml" ] && [ -f "$candidate/.env" ] && {
      BUILD="$candidate"
      break
    }
  done
fi
[ -n "${BUILD:-}" ] || { echo "ERROR: no usable build directory found (set BUILD_DIR)"; exit 1; }
BUILD="$(ls -d "$BUILD" | tail -1)"
cd "$BUILD"
echo "using target compose context: $BUILD"

for f in "$BUILD/.env" "$BUILD/docker-compose.production.yml"; do
  [ -f "$f" ] || { echo "ERROR: required rollback context file missing: $f"; exit 1; }
done

target_services=(api web worker scheduler)
for service in "${target_services[@]}"; do
  grep -Eq "^[[:space:]]*$service:|^[[:space:]]{2}$service:" "$PIN" || {
    echo "ERROR: target pin does not declare service $service"
    exit 1
  }
done

target_images="$(grep -o 'puregamma-ai-\(api\|web\|worker\|scheduler\):[0-9a-zA-Z._-]*' "$PIN" | sort -u)"
[ "$(printf '%s\n' "$target_images" | sed '/^$/d' | wc -l)" -eq 4 ] || {
  echo "ERROR: target pin must contain exactly four immutable application images"
  exit 1
}
while read -r image; do
  [ -n "$image" ] || continue
  docker image inspect "$image" >/dev/null || {
    echo "ERROR: target image $image is not present locally"
    exit 1
  }
done <<< "$target_images"

TARGET_OVERRIDE="/puregamma/docker-compose.rollback-target-$STAMP.yml"
cp "$PIN" "$TARGET_OVERRIDE"
chmod 600 "$TARGET_OVERRIDE"
TARGET_DC=(docker compose --env-file "$BUILD/.env" -f "$BUILD/docker-compose.production.yml" -f "$TARGET_OVERRIDE")
"${TARGET_DC[@]}" config --quiet

# Capture what is ACTUALLY running before changing anything. This is the rescue
# target if the rollback candidate fails its health/readiness checks.
RESCUE="/puregamma/override-$STAMP-before-rollback-rescue.yml"
{
  echo "# Rescue pins captured immediately before rollback $STAMP"
  echo "services:"
  for service in "${target_services[@]}"; do
    if [ -f "$LIVE_BUILD/docker-compose.production.yml" ] && [ -f "$LIVE_BUILD/.env" ]; then
      id="$(docker compose --env-file "$LIVE_BUILD/.env" -f "$LIVE_BUILD/docker-compose.production.yml" ps -q "$service" 2>/dev/null || true)"
    else
      id="$(docker ps --filter "name=puregamma-ai-$service" --format '{{.ID}}' | head -1)"
    fi
    [ -n "$id" ] || { echo "ERROR: live service $service has no running container"; exit 1; }
    image="$(docker inspect -f '{{.Config.Image}}' "$id")"
    [ -n "$image" ] || { echo "ERROR: cannot resolve live image for $service"; exit 1; }
    printf '  %s:\n    image: %s\n' "$service" "$image"
  done
} > "$RESCUE"
chmod 600 "$RESCUE"
echo "rescue pin: $RESCUE"

RESTORE_ATTEMPTED=false
restore_previous_release() {
  rc=$?
  if [ "$rc" -eq 0 ] || [ "$RESTORE_ATTEMPTED" = "true" ]; then
    return "$rc"
  fi
  RESTORE_ATTEMPTED=true
  trap - ERR
  echo "ERROR: rollback candidate failed verification; attempting rescue restore" >&2
  rescue_context="$LIVE_BUILD"
  if [ ! -f "$rescue_context/docker-compose.production.yml" ] || [ ! -f "$rescue_context/.env" ]; then
    rescue_context="$BUILD"
  fi
  RESCUE_DC=(docker compose --env-file "$rescue_context/.env" -f "$rescue_context/docker-compose.production.yml" -f "$RESCUE")
  "${RESCUE_DC[@]}" config --quiet
  "${RESCUE_DC[@]}" up -d --no-deps api web worker scheduler || true
  echo "Rescue restore was attempted from $RESCUE; verify service health immediately." >&2
  exit "$rc"
}
trap restore_previous_release ERR

echo "=== rolling back to target pins ==="
cat "$TARGET_OVERRIDE"
"${TARGET_DC[@]}" up -d --no-deps api web worker scheduler

wait_running() {
  local service="$1"
  local attempts="${2:-40}"
  local id status health
  for ((i=1; i<=attempts; i++)); do
    id="$("${TARGET_DC[@]}" ps -q "$service")"
    if [ -n "$id" ]; then
      status="$(docker inspect -f '{{.State.Status}}' "$id")"
      health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$id")"
      if [ "$status" = "running" ] && { [ "$health" = "none" ] || [ "$health" = "healthy" ]; }; then
        echo "$service: running health=$health"
        return 0
      fi
      if [ "$status" = "exited" ] || [ "$status" = "dead" ] || [ "$health" = "unhealthy" ]; then
        echo "ERROR: $service entered status=$status health=$health" >&2
        return 1
      fi
    fi
    sleep 3
  done
  echo "ERROR: $service did not become ready" >&2
  return 1
}

for service in "${target_services[@]}"; do
  wait_running "$service"
done

echo "=== verifying API readiness inside rolled-back container ==="
"${TARGET_DC[@]}" exec -T api python -c \
  'import json, urllib.request; data=json.load(urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=5)); assert data.get("status") == "ok", data; print(json.dumps(data, sort_keys=True))'

echo "=== verifying web health inside rolled-back container ==="
"${TARGET_DC[@]}" exec -T web node -e \
  'fetch("http://127.0.0.1:3000/health").then(r => { if (!r.ok) process.exit(1); console.log("web health", r.status) }).catch(() => process.exit(1))'

trap - ERR
cp "$TARGET_OVERRIDE" /puregamma/docker-compose.v41-override.yml
docker ps --filter 'name=puregamma-ai-' --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
echo "=== rollback verified $(date -u +%FT%TZ) ==="
echo "rescue pin retained at: $RESCUE"
