"""Probe the deployed chat-workspace behaviour in a real HTTP session.

Not a test file: it prints what happens so a defect can be attributed. Run with
the repository venv from the project root.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("ENABLE_MOCK_MARKET_DATA", "true")
os.environ["ENABLE_MOCK_AGENT"] = "true"
sys.path.insert(0, os.path.abspath("."))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.dependencies import create_access_token, get_db
from apps.api.main import app
from packages.database.models import AgentAttachmentRecord, Base, User
from packages.database.seed import seed_all

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
db = Session()
seed_all(db)

user = User(email="probe@example.invalid", name="probe", role="user", plan="Free", credit_balance=500)
db.add(user)
db.commit()
db.refresh(user)
headers = {"Authorization": f"Bearer {create_access_token(user)}"}


def override_db():
    yield db


app.dependency_overrides[get_db] = override_db
client = TestClient(app)


def show(label, response):
    body = response.text
    print(f"{label}: {response.status_code} {body[:220]}")


print("--- 1. upload a small file and check the quota arithmetic ---")
small = client.post("/api/agent/attachments?name=small.txt", content=b"hello world", headers=headers)
show("upload", small)
attachment = small.json()["attachment"]

print("--- 2. upload something over the per-file limit ---")
big = client.post("/api/agent/attachments?name=big.txt", content=b"x" * (10 * 1024 * 1024 + 1), headers=headers)
show("oversize", big)

print("--- 3. fill the account quota with files just under the limit ---")
made = []
for index in range(11):
    response = client.post(
        f"/api/agent/attachments?name=fill-{index}.txt",
        content=b"y" * (9 * 1024 * 1024),
        headers=headers,
    )
    made.append(response.status_code)
print("fill statuses:", made)
used = db.query(AgentAttachmentRecord).filter_by(user_id=user.id).count()
print("rows stored:", used, "total bytes:", db.query(AgentAttachmentRecord).filter_by(user_id=user.id).with_entities(AgentAttachmentRecord.size).all()[-1])
quota = client.post("/api/agent/attachments?name=one-more.txt", content=b"z", headers=headers)
show("one more after quota", quota)

print("--- 4. can the user free that space? ---")
freed = client.delete(f"/api/agent/attachments/{attachment['id']}", headers=headers)
print("DELETE attachment:", freed.status_code, freed.text[:160])
after = client.get(f"/api/agent/attachments/{attachment['id']}/content", headers=headers)
print("download after removal:", after.status_code, after.text[:80])
files = client.get("/api/agent/workspace-capabilities", headers=headers)
print("capabilities after removal:", files.status_code)

print("--- 4b. upload again after freeing (the dead-end must be gone) ---")
refill = client.post("/api/agent/attachments?name=refill.txt", content=b"z" * 1024, headers=headers)
print("refill:", refill.status_code, refill.text[:120])

print("--- 5. a conversation turn with a stored attachment: does it reach the model and survive? ---")
conversation = client.post("/api/agent/conversations", json={}, headers=headers).json()["conversation"]
stored = client.post("/api/agent/attachments?name=stored.txt", content=b"the answer is 42", headers=headers).json()["attachment"]
message = client.post(
    f"/api/agent/conversations/{conversation['id']}/messages",
    json={"content": "what is in the file", "attachments": [{"id": stored["id"]}], "research_mode": True},
    headers=headers,
)
print("send:", message.status_code)
events = [line for line in message.text.splitlines() if line.startswith("event: ")]
print("events:", events[:20])
read_back = client.get(f"/api/agent/conversations/{conversation['id']}", headers=headers).json()
for row in read_back["messages"]:
    print("message", row["role"], "| content:", row["content"][:60], "| attachments:", row["context"].get("attachments"))

print("--- 5b. sending a draft whose file was deleted must not fail the turn ---")
ghost = client.post("/api/agent/attachments?name=ghost.txt", content=b"gone", headers=headers).json()["attachment"]
client.delete(f"/api/agent/attachments/{ghost['id']}", headers=headers)
ghost_turn = client.post(
    f"/api/agent/conversations/{conversation['id']}/messages",
    json={"content": "still there?", "attachments": [{"id": ghost["id"]}], "research_mode": True},
    headers=headers,
)
print("send with a removed draft:", ghost_turn.status_code, ghost_turn.text[:120].replace("\n", " "))

print("--- 6. deleting a conversation frees the bytes it had sent ---")
before = db.query(AgentAttachmentRecord).filter_by(user_id=user.id, size=0).count()
print("freed rows before:", before)
response = client.delete(f"/api/agent/conversations/{conversation['id']}", headers=headers)
print("delete conversation:", response.status_code, response.text[:160])
print("rows now with size 0 (freed):", db.query(AgentAttachmentRecord).filter_by(user_id=user.id, size=0).count())

app.dependency_overrides.clear()
db.close()
