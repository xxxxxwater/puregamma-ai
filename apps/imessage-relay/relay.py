from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from config import settings


class SendRequest(BaseModel):
    recipient: str
    message: str
    idempotency_key: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deliveries (
                idempotency_key TEXT PRIMARY KEY,
                recipient TEXT NOT NULL,
                message_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                provider_response TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT,
                next_retry_at TEXT,
                last_error TEXT
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(deliveries)").fetchall()}
        for name, ddl in (("attempt_count", "INTEGER NOT NULL DEFAULT 0"), ("last_attempt_at", "TEXT"), ("next_retry_at", "TEXT"), ("last_error", "TEXT")):
            if name not in columns:
                conn.execute(f"ALTER TABLE deliveries ADD COLUMN {name} {ddl}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.relay_secret:
        raise RuntimeError("IMESSAGE_RELAY_SECRET is required")
    init_db()
    yield


app = FastAPI(title="PureGamma AI iMessage Relay", version="0.1.0", lifespan=lifespan)


def compute_hmac(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify_signature(timestamp: str | None, signature: str | None, body: bytes) -> bool:
    if not timestamp or not signature or not settings.relay_secret:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > settings.replay_tolerance_seconds:
        return False
    expected = compute_hmac(settings.relay_secret, timestamp, body)
    return hmac.compare_digest(expected, signature)


def existing_delivery(idempotency_key: str) -> dict | None:
    with sqlite3.connect(settings.db_path) as conn:
        row = conn.execute(
            "SELECT idempotency_key, recipient, status, provider_response, created_at, attempt_count, last_attempt_at, next_retry_at, last_error FROM deliveries WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
    if not row:
        return None
    return {
        "idempotency_key": row[0],
        "recipient": row[1],
        "status": row[2],
        "provider_response": json.loads(row[3]),
        "created_at": row[4],
        "attempt_count": row[5],
        "last_attempt_at": row[6],
        "next_retry_at": row[7],
        "last_error": row[8],
        "duplicate": True,
    }


def record_delivery(idempotency_key: str, recipient: str, message: str, status: str, provider_response: dict, attempt_count: int, next_retry_at: str | None, last_error: str | None) -> None:
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            """
            INSERT INTO deliveries (idempotency_key, recipient, message_hash, status, provider_response, created_at, attempt_count, last_attempt_at, next_retry_at, last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(idempotency_key) DO UPDATE SET status=excluded.status, provider_response=excluded.provider_response, attempt_count=excluded.attempt_count, last_attempt_at=excluded.last_attempt_at, next_retry_at=excluded.next_retry_at, last_error=excluded.last_error
            """,
            (
                idempotency_key,
                recipient,
                hashlib.sha256(message.encode()).hexdigest(),
                status,
                json.dumps(provider_response),
                now_iso(),
                attempt_count,
                now_iso(),
                next_retry_at,
                last_error,
            ),
        )


def send_via_messages_app(recipient: str, message: str) -> dict:
    if platform.system() != "Darwin":
        return {"ok": False, "status": "unsupported_os"}
    if not os.path.exists(settings.applescript_path):
        return {"ok": False, "status": "missing_applescript"}
    completed = subprocess.run(
        ["osascript", settings.applescript_path, recipient, message],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    if completed.returncode != 0:
        return {"ok": False, "status": "failed", "stderr": completed.stderr.strip()}
    return {"ok": True, "status": "sent", "stdout": completed.stdout.strip()}


@app.get("/health")
def health() -> dict:
    init_db()
    return {"status": "ok", "service": "puregamma-imessage-relay", "os": platform.system(), "secret_configured": bool(settings.relay_secret)}


@app.get("/deliveries/{idempotency_key}")
def delivery_status(idempotency_key: str, x_pg_timestamp: str | None = Header(default=None, alias="X-PG-Timestamp"), x_pg_signature: str | None = Header(default=None, alias="X-PG-Signature")) -> dict:
    init_db()
    if not verify_signature(x_pg_timestamp, x_pg_signature, b""):
        raise HTTPException(status_code=401, detail="invalid_hmac_signature")
    row = existing_delivery(idempotency_key)
    if not row:
        raise HTTPException(status_code=404, detail="delivery_not_found")
    return row


@app.post("/send")
async def send(
    request: Request,
    x_pg_timestamp: str | None = Header(default=None, alias="X-PG-Timestamp"),
    x_pg_signature: str | None = Header(default=None, alias="X-PG-Signature"),
    x_pg_idempotency_key: str | None = Header(default=None, alias="X-PG-Idempotency-Key"),
) -> dict:
    init_db()
    body = await request.body()
    if not verify_signature(x_pg_timestamp, x_pg_signature, body):
        raise HTTPException(status_code=401, detail="invalid_hmac_signature")
    payload = SendRequest(**json.loads(body.decode()))
    if x_pg_idempotency_key and x_pg_idempotency_key != payload.idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key_mismatch")
    if len(payload.message) > settings.max_message_length:
        raise HTTPException(status_code=400, detail="message_too_long")
    if not re.fullmatch(r"\+[1-9]\d{7,14}", payload.recipient):
        raise HTTPException(status_code=400, detail="invalid_recipient")
    duplicate = existing_delivery(payload.idempotency_key)
    if duplicate and duplicate["status"] == "sent":
        return duplicate
    if duplicate and duplicate["status"] == "failed_retryable" and duplicate.get("next_retry_at") and datetime.fromisoformat(duplicate["next_retry_at"]) > datetime.now(timezone.utc):
        return duplicate
    attempt_count = int(duplicate.get("attempt_count", 0) if duplicate else 0) + 1
    provider_response = send_via_messages_app(payload.recipient, payload.message)
    raw_status = provider_response["status"]
    permanent = raw_status in {"unsupported_os", "missing_applescript", "invalid_recipient"}
    status = "sent" if provider_response.get("ok") else "failed_permanent" if permanent or attempt_count >= 3 else "failed_retryable"
    delays = (1, 5, 30)
    next_retry_at = (datetime.now(timezone.utc) + timedelta(minutes=delays[min(attempt_count - 1, 2)])).isoformat() if status == "failed_retryable" else None
    record_delivery(payload.idempotency_key, payload.recipient, payload.message, status, {"ok": provider_response.get("ok", False), "status": raw_status}, attempt_count, next_retry_at, None if status == "sent" else raw_status)
    return {
        "idempotency_key": payload.idempotency_key,
        "recipient": payload.recipient,
        "status": status,
        "provider_response": {"ok": provider_response.get("ok", False), "status": raw_status},
        "attempt_count": attempt_count,
        "next_retry_at": next_retry_at,
        "duplicate": False,
    }
