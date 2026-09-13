#!/usr/bin/env bash
# Mint a disposable live session for the browser acceptance run and clean it up.
#
#   bash /puregamma/release-live-session.sh create   -> prints "TOKEN=<jwt> USER_ID=<id>"
#   bash /puregamma/release-live-session.sh delete   -> removes the account and its rows
set -Eeuo pipefail

BUILD=/puregamma/build-6a9e924f
ACTION="${1:-create}"
cd "$BUILD"

DC=(docker compose --env-file "$BUILD/.env" -f "$BUILD/docker-compose.production.yml" -f "$BUILD/docker-compose.v41-override.yml")

if [ "$ACTION" = "create" ]; then
"${DC[@]}" run --rm --no-deps -T api python - <<'PY'
from apps.api.dependencies import create_access_token
from packages.database.models import AgentConversation, User
from packages.database.session import SessionLocal

email = "live-acceptance@example.invalid"
session = SessionLocal()
existing = session.query(User).filter(User.email == email).one_or_none()
if existing is not None:
    # A fresh session_version invalidates every token minted for the old one.
    existing.session_version = (existing.session_version or 0) + 1
    existing.credit_balance = 500
    session.commit()
    user = existing
else:
    user = User(email=email, name="live-acceptance", role="user", plan="Free", credit_balance=500)
    session.add(user)
    session.commit()
    session.refresh(user)
token = create_access_token(user)
print(f"TOKEN={token}")
print(f"USER_ID={user.id}")
session.close()
PY
elif [ "$ACTION" = "delete" ]; then
"${DC[@]}" run --rm --no-deps -T api python - <<'PY'
from packages.database.models import (AgentAttachmentRecord, AgentConversation, AgentMessage, AgentRun,
                                      AgentToolCall, User)
from packages.database.session import SessionLocal

email = "live-acceptance@example.invalid"
session = SessionLocal()
user = session.query(User).filter(User.email == email).one_or_none()
if user is None:
    print("nothing to delete")
else:
    run_ids = [row.id for row in session.query(AgentRun).filter(AgentRun.user_id == user.id).all()]
    if run_ids:
        session.query(AgentToolCall).filter(AgentToolCall.run_id.in_(run_ids)).delete(synchronize_session=False)
    session.query(AgentAttachmentRecord).filter(AgentAttachmentRecord.user_id == user.id).delete(synchronize_session=False)
    session.query(AgentMessage).filter(AgentMessage.user_id == user.id).delete(synchronize_session=False)
    session.query(AgentRun).filter(AgentRun.user_id == user.id).delete(synchronize_session=False)
    session.query(AgentConversation).filter(AgentConversation.user_id == user.id).delete(synchronize_session=False)
    session.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    session.commit()
    print("deleted, remaining rows for that address:", session.query(User).filter(User.email == email).count())
session.close()
PY
else
  echo "usage: $0 create|delete" >&2
  exit 2
fi
