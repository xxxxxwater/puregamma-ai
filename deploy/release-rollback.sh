#!/usr/bin/env bash
# Roll back the four PUREGAMMA services to a recorded set of pins.
#
#   bash /puregamma/release-rollback.sh /puregamma/override-<stamp>-before-<short>.yml
#
# The database is NOT rolled back: 0032 is additive and forward-only, and its
# downgrade deliberately refuses to drop the attachments table. Older images
# ignore the new table and the new columns, so a code rollback is safe while the
# schema stays at 0032.
#
# Data safety on the way back: a version that predates the attachment endpoints
# cannot serve or release the files already stored, so those rows are left
# exactly as they are. Nothing here deletes data.
set -Eeuo pipefail

PIN="${1:?usage: release-rollback.sh /puregamma/override-<stamp>-before-<short>.yml}"
[ -f "$PIN" ] || { echo "ERROR: pin file $PIN not found"; exit 1; }

# The compose context only needs to exist and carry .env + the compose files;
# which build-* directory it is does not change the pinned images. Prefer the
# directory the pin names, then the newest one that is complete.
BUILD="${BUILD_DIR:-}"
if [ -z "$BUILD" ]; then
  named="$(basename "$PIN" | sed -n 's/.*-\([0-9a-f]\{7,40\}\)\.yml$/\1/p')"
  for candidate in "/puregamma/build-$named" /puregamma/build-*; do
    [ -f "$candidate/docker-compose.production.yml" ] && [ -f "$candidate/.env" ] && { BUILD="$candidate"; break; }
  done
fi
[ -n "${BUILD:-}" ] || { echo "ERROR: no usable build directory found (set BUILD_DIR)"; exit 1; }
BUILD="$(ls -d "$BUILD" | tail -1)"
cd "$BUILD"
echo "using compose context: $BUILD"

echo "=== rolling back to the pins in $PIN ==="
cat "$PIN"
while read -r image; do
  docker image inspect "$image" >/dev/null || { echo "ERROR: $image is not present locally"; exit 1; }
done < <(grep -o 'puregamma-ai-[a-z]*:[0-9a-zA-Z._-]*' "$PIN")

cp "$PIN" /puregamma/docker-compose.v41-override.yml
docker compose --env-file "$BUILD/.env" \
  -f "$BUILD/docker-compose.production.yml" \
  -f /puregamma/docker-compose.v41-override.yml \
  up -d --no-deps api web worker scheduler

sleep 15
docker ps --filter 'name=puregamma-ai-' --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
echo "=== rollback applied $(date -u +%FT%TZ) ==="
