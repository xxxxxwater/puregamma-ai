#!/usr/bin/env bash
# Roll back the four PUREGAMMA services to a recorded set of pins.
#
#   bash /puregamma/release-rollback.sh /puregamma/override-<stamp>-before-<short>.yml
#
# The database is NOT rolled back: 0032 is additive and forward-only, and its
# downgrade deliberately refuses to drop the attachments table. Older images
# ignore the new table and the new columns, so a code rollback is safe while the
# schema stays at 0032.
set -Eeuo pipefail

PIN="${1:?usage: release-rollback.sh /puregamma/override-<stamp>.yml}"
[ -f "$PIN" ] || { echo "ERROR: pin file $PIN not found"; exit 1; }
BUILD=/puregamma/build-6a9e924f
cd "$BUILD"

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
