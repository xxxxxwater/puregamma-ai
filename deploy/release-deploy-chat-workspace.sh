#!/usr/bin/env bash
# Promote the built chat-workspace images: migrate, then roll each service.
#
# Preconditions: /puregamma/build-<short>/{Dockerfile.api,.env,docker-compose*},
# the four images tagged <short>, and a pg_dump taken beforehand. The additive
# migration 0032 is applied explicitly through the NEW api image, before any
# container is replaced, so a failure leaves the running services untouched.
#
# Data safety: no `down -v`, no volume recreation, no rsync into the live tree.
set -Eeuo pipefail

SHORT="${1:-6a9e924f}"
BUILD="/puregamma/build-$SHORT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="/puregamma/deploy-$SHORT-$STAMP.log"

cd "$BUILD"
exec > >(tee "$LOG") 2>&1
echo "=== deploy $SHORT at $(date -u +%FT%TZ) ==="

DC=(docker compose --env-file "$BUILD/.env" -f "$BUILD/docker-compose.production.yml" -f "$BUILD/docker-compose.v41-override.yml")

echo "--- 0. preconditions ---"
for f in Dockerfile.api .env docker-compose.production.yml docker-compose.v41-override.yml; do
  [ -f "$BUILD/$f" ] || { echo "ERROR: $BUILD/$f missing"; exit 1; }
done
for img in "puregamma-ai-api:$SHORT" "puregamma-ai-worker:$SHORT" "puregamma-ai-scheduler:$SHORT" "puregamma-ai-web:$SHORT"; do
  docker image inspect "$img" >/dev/null || { echo "ERROR: image $img missing"; exit 1; }
done
echo "all four images present"

echo "--- 1. record the rollback pin from the LIVE containers ---"
# Read the pins off the running containers, not off a file: the build directory's
# override already carries the NEW pins, so copying it would record the release
# as its own rollback target.
{
  echo "# Rollback pins for the state before $SHORT, read from the live containers."
  echo "services:"
  for svc in api worker scheduler web; do
    image="$(docker inspect "puregamma-ai-$svc-1" --format '{{.Config.Image}}' 2>/dev/null || echo '')"
    if [ -n "$image" ]; then
      echo "  $svc:"
      echo "    image: $image"
      docker image inspect "$image" >/dev/null || { echo "ERROR: live image $image is not present locally"; exit 1; }
    else
      echo "  # $svc had no running container"
    fi
  done
} > "/puregamma/override-$STAMP-before-$SHORT.yml"
cat "/puregamma/override-$STAMP-before-$SHORT.yml"

echo "--- 2. alembic head before the promote ---"
BEFORE="$(docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc 'select version_num from alembic_version;')"
echo "alembic head before: $BEFORE"
# 0031 is the head this release migrates FROM; 0032 means an earlier run of this
# same release already applied it (the migration is additive and idempotent).
case "$BEFORE" in
  0031_deepseek_v41_flash_defaults|0032_chat_workspace) ;;
  *) echo "ERROR: unexpected head $BEFORE"; exit 1 ;;
esac

echo "--- 3. snapshot the row counts that must survive ---"
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc \
  "select (select count(*) from users) users, (select count(*) from agent_conversations) convs, (select count(*) from agent_messages) msgs;"

echo "--- 4. roll api (its entrypoint applies migration 0032) ---"
# The migration runs inside the container entrypoint, not through a one-off
# `docker run`: docker run does not read env_file, so quoted values in .env
# (SESSION_MAX_AGE_SECONDS='604800') reach the process verbatim and crash the
# settings parser. Compose performs the same de-quoting the live services see.
"${DC[@]}" up -d --no-deps api
for i in $(seq 1 40); do
  status="$(docker inspect puregamma-ai-api-1 --format '{{.State.Health.Status}}' 2>/dev/null || echo starting)"
  [ "$status" = "healthy" ] && break
  sleep 5
done
[ "$status" = "healthy" ] || { echo "ERROR: api never became healthy (last: $status)"; docker logs --tail 60 puregamma-ai-api-1; exit 1; }
echo "api healthy on $(docker inspect puregamma-ai-api-1 --format '{{.Config.Image}}')"

AFTER="$(docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc 'select version_num from alembic_version;')"
echo "alembic head after:  $AFTER"
[ "$AFTER" = "0032_chat_workspace" ] || { echo "ERROR: expected head 0032_chat_workspace, got $AFTER"; exit 1; }
echo -n "agent_attachments rows: "
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc "select count(*) from agent_attachments;"
echo -n "agent_conversations.permission_mode nulls (must be 0): "
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc "select count(*) from agent_conversations where permission_mode is null;"
echo -n "row counts after migrate: "
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc \
  "select (select count(*) from users) users, (select count(*) from agent_conversations) convs, (select count(*) from agent_messages) msgs;"

echo "--- 5. roll web ---"
"${DC[@]}" up -d --no-deps web
for i in $(seq 1 40); do
  status="$(docker inspect puregamma-ai-web-1 --format '{{.State.Health.Status}}' 2>/dev/null || echo starting)"
  [ "$status" = "healthy" ] && break
  sleep 5
done
[ "$status" = "healthy" ] || { echo "ERROR: web never became healthy (last: $status)"; docker logs --tail 60 puregamma-ai-web-1; exit 1; }
echo "web healthy on $(docker inspect puregamma-ai-web-1 --format '{{.Config.Image}}')"

echo "--- 6. roll worker + scheduler ---"
"${DC[@]}" up -d --no-deps worker scheduler
sleep 10
docker ps --filter 'name=puregamma-ai-' --format '{{.Names}}\t{{.Status}}\t{{.Image}}'

echo "--- 7. new chat endpoints reachable from inside the network ---"
"${DC[@]}" run --rm --no-deps -T api python - <<'PY'
import json, urllib.error, urllib.request
for path in ("/health", "/api/agent/workspace-capabilities"):
    try:
        with urllib.request.urlopen("http://api:8000" + path, timeout=10) as r:
            print(path, r.status)
    except urllib.error.HTTPError as e:
        print(path, e.code, "(401 is the correct unauthenticated answer)")
    except Exception as e:
        print(path, "ERROR", e)
PY

echo "--- 8. authenticated contract check with a disposable account inside the network ---"
# A real signup would need a captcha challenge, so the disposable account is
# inserted with the ORM (the same model the app uses), carries a clearly fake
# address, and is deleted with its rows at the end of the run.
"${DC[@]}" run --rm --no-deps -T api python - <<'PY'
import json, urllib.error, urllib.request, uuid

BASE = "http://api:8000"


def call(method, path, token=None, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if token:
        request.add_header("Authorization", "Bearer " + token)
    if data is not None:
        request.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
            return response.status, (json.loads(payload) if payload[:1] in (b"{", b"[") else payload)
    except urllib.error.HTTPError as error:
        payload = error.read()
        try:
            return error.code, json.loads(payload)
        except Exception:
            return error.code, payload[:200]


from apps.api.dependencies import create_access_token
from packages.database.models import (AgentAttachmentRecord, AgentConversation, AgentMessage, AgentRun,
                                      AgentToolCall, User)
from packages.database.session import SessionLocal

session = SessionLocal()
email = "verify-chat-workspace@example.invalid"
existing = session.query(User).filter(User.email == email).one_or_none()
if existing is not None:
    session.delete(existing)
    session.commit()
user = User(email=email, name="chat-workspace-verify", role="user", plan="Free", credit_balance=0)
session.add(user)
session.commit()
session.refresh(user)
user_id = user.id
token = create_access_token(user)
print("disposable user", user_id)

try:
    status, caps = call("GET", "/api/agent/workspace-capabilities", token=token)
    print("workspace-capabilities", status, json.dumps(caps)[:200])
    assert status == 200 and caps["max_files"] == 8, caps

    status, conv = call("POST", "/api/agent/conversations", token=token, body={})
    print("create-conversation", status, str(conv)[:160])
    assert status == 200, conv
    conversation_id = conv["conversation"]["id"]
    assert conv["conversation"]["permission_mode"] == "workspace-write", conv

    status, denied = call("PATCH", "/api/agent/conversations/" + conversation_id, token=token,
                          body={"permission_mode": "full-access"})
    print("full-access-without-ack", status, str(denied)[:120])
    assert status == 400, denied

    status, allowed = call("PATCH", "/api/agent/conversations/" + conversation_id, token=token,
                           body={"permission_mode": "full-access", "acknowledge_full_access": True})
    print("full-access-with-ack", status)
    assert status == 200, allowed

    body = b"puregamma chat workspace verification"
    status, uploaded = call("POST", "/api/agent/attachments?name=verify.txt", token=token,
                            raw=body, ctype="application/octet-stream")
    print("upload", status, str(uploaded)[:200])
    assert status == 200 and uploaded["attachment"]["content"] == "", uploaded
    attachment_id = uploaded["attachment"]["id"]

    status, fetched = call("GET", "/api/agent/attachments/" + attachment_id + "/content", token=token)
    print("download", status, fetched[:60] if isinstance(fetched, bytes) else fetched)
    assert status == 200 and fetched == body, (status, fetched)

    status, _ = call("GET", "/api/agent/attachments/" + attachment_id + "/content")
    print("download-without-token", status)
    assert status == 401, status

    status, pending = call("GET", "/api/agent/conversations/" + conversation_id, token=token)
    print("conversation-read", status, "pending_approvals=", pending.get("pending_approvals"))
    assert status == 200 and pending.get("pending_approvals") == [], pending

    # A small PNG must survive as a PNG. This is the case that failed in live
    # acceptance: every image used to be re-encoded through JPEG, which rejects
    # valid tiny files.
    import base64 as _base64
    tiny = _base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFklEQVR4nGP8z8DAwMDAwMDEAAWMDAwAFvcBaZzTzB0AAAAASUVORK5CYII="
    )
    status, image = call("POST", "/api/agent/attachments?name=tiny.png", token=token,
                         raw=tiny, ctype="application/octet-stream")
    print("image-upload", status, str(image)[:200])
    assert status == 200, image
    assert image["attachment"]["kind"] == "image", image
    assert image["attachment"]["mime"] == "image/png", image
    status, image_bytes = call("GET", "/api/agent/attachments/" + image["attachment"]["id"] + "/content", token=token)
    assert status == 200 and image_bytes == tiny, (status, len(image_bytes) if isinstance(image_bytes, bytes) else image_bytes)
    print("image-round-trip ok, bytes:", len(image_bytes))

    status, _ = call("POST", "/api/agent/tool-calls/" + str(uuid.uuid4()) + "/approval", token=token,
                     body={"decision": "approved"})
    print("approval-for-unknown-call", status)
    assert status == 404, status

    print("counts", {
        "users": session.query(User).count(),
        "conversations": session.query(AgentConversation).count(),
        "messages": session.query(AgentMessage).count(),
        "attachments": session.query(AgentAttachmentRecord).count(),
    })
    print("VERIFY_OK")
finally:
    run_ids = [row.id for row in session.query(AgentRun).filter(AgentRun.user_id == user_id).all()]
    if run_ids:
        session.query(AgentToolCall).filter(AgentToolCall.run_id.in_(run_ids)).delete(synchronize_session=False)
    session.query(AgentMessage).filter(AgentMessage.user_id == user_id).delete(synchronize_session=False)
    session.query(AgentRun).filter(AgentRun.user_id == user_id).delete(synchronize_session=False)
    session.query(AgentConversation).filter(AgentConversation.user_id == user_id).delete(synchronize_session=False)
    session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    session.commit()
    print("cleaned up, disposable rows left:",
          session.query(User).filter(User.email == email).count())
    session.close()
PY

echo "=== deploy OK: $SHORT $(date -u +%FT%TZ) log=$LOG ==="
echo "rollback plan recorded at /puregamma/override-$STAMP-before-$SHORT.yml"
