#!/usr/bin/env bash
# Server-side extraction and image build for the chat-workspace release.
#
# Mirrors the recorded round8b method: the tree is exported from the bare mirror
# at /puregamma/.git-mirror, so what is built is exactly the commit — nothing is
# rsynced into the live tree.
#
#   /puregamma/build-<short>/            exported source + the compose files
#   puregamma-ai-api:<short>             api / worker / scheduler image
#   puregamma-ai-web:<short>             web image
#   /puregamma/build-<short>.log         full build output
#
# Nothing here touches the running services or the database.
set -Eeuo pipefail

SHORT="${1:-6a9e924f}"
BUILD="/puregamma/build-$SHORT"
MIRROR=/puregamma/.git-mirror
REF="refs/remotes/origin/main"

exec > >(tee "$BUILD.log") 2>&1

echo "=== release build: $SHORT $(date -u +%FT%TZ) ==="

echo "--- 1. fetch the mirror ---"
git --git-dir="$MIRROR" fetch --prune origin '+refs/heads/*:refs/remotes/origin/*'
FULL="$(git --git-dir="$MIRROR" rev-parse "$REF")"
echo "mirror $REF = $FULL"
if [ "${FULL:0:8}" != "$SHORT" ]; then
  echo "ERROR: mirror main is ${FULL:0:8}, expected $SHORT — refusing to build the wrong commit."
  exit 1
fi

echo "--- 2. export the exact commit ---"
rm -rf "$BUILD"
mkdir -p "$BUILD"
git --git-dir="$MIRROR" archive "$FULL" | tar -x -C "$BUILD"

echo "--- 3. per-service pins + production env ---"
cp /puregamma/app/docker-compose.production.yml "$BUILD/docker-compose.production.yml"
cp /puregamma/app/docker-compose.v41-override.yml "$BUILD/docker-compose.v41-override.yml"
cp /puregamma/app/.env "$BUILD/.env"
chmod 600 "$BUILD/.env"
sed -i "s/puregamma-ai-\(api\|worker\|scheduler\|web\):[0-9a-f]\{8\}/puregamma-ai-\1:$SHORT/g" "$BUILD/docker-compose.v41-override.yml"
echo "--- override now ---"
cat "$BUILD/docker-compose.v41-override.yml"

echo "--- 4. prove the exported tree matches the commit ---"
for f in apps/api/services/chat_workspace.py apps/web/components/chat-workspace-composer.tsx \
         packages/database/alembic/versions/0032_chat_workspace.py apps/api/requirements.txt; do
  want="$(git --git-dir="$MIRROR" rev-parse "$FULL:$f")"
  got="$(git --git-dir="$MIRROR" hash-object "$BUILD/$f")"
  if [ "$want" != "$got" ]; then
    echo "ERROR: $f in the exported tree is not the commit blob ($want vs $got)"
    exit 1
  fi
  echo "ok $f = ${got:0:12}"
done

echo "--- 5. build api / worker / scheduler image ---"
docker build --file "$BUILD/Dockerfile.api" \
  --build-arg INSTALL_DOCKER_CLI=false \
  --tag "puregamma-ai-api:$SHORT" "$BUILD"
docker tag "puregamma-ai-api:$SHORT" "puregamma-ai-worker:$SHORT"
docker tag "puregamma-ai-api:$SHORT" "puregamma-ai-scheduler:$SHORT"

echo "--- 6. build web image ---"
docker build --file "$BUILD/apps/web/Dockerfile" \
  --build-arg NEXT_PUBLIC_API_URL="https://api.puregamma.ai" \
  --build-arg NEXT_PUBLIC_SITE_URL="https://app.puregamma.ai" \
  --build-arg NEXT_PUBLIC_INITIAL_LAUNCH_MODE=true \
  --build-arg NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=false \
  --tag "puregamma-ai-web:$SHORT" "$BUILD"

echo "--- 7. prove the images carry the new code ---"
docker run --rm --entrypoint sh "puregamma-ai-api:$SHORT" -c \
  "grep -c 'def tool_permission' apps/api/services/chat_workspace.py; grep -rl 'pypdf' apps/api/requirements.txt; python -c 'import pypdf, PIL; print(\"pypdf\", pypdf.__version__, \"Pillow\", PIL.__version__)'"
docker run --rm --entrypoint sh "puregamma-ai-web:$SHORT" -c \
  "grep -rl 'chat-composer-input' .next-build/static 2>/dev/null | head -3; ls .next-build/standalone/server.js"

echo "--- 8. image ids ---"
docker image inspect "puregamma-ai-api:$SHORT" --format 'api {{.Id}}'
docker image inspect "puregamma-ai-web:$SHORT" --format 'web {{.Id}}'

echo "=== build OK: $SHORT $(date -u +%FT%TZ) ==="
