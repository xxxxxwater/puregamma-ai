from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from config import settings


app = FastAPI(title="PureGamma.ai iMessage Relay", version="0.1.0")


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
                created_at TEXT NOT NULL
            )
            """
        )


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
            "SELECT idempotency_key, recipient, status, provider_response, created_at FROM deliveries WHERE idempotency_key = ?",
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
        "duplicate": True,
    }


def record_delivery(idempotency_key: str, recipient: str, message: str, status: str, provider_response: dict) -> None:
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO deliveries (idempotency_key, recipient, message_hash, status, provider_response, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                idempotency_key,
                recipient,
                hashlib.sha256(message.encode()).hexdigest(),
                status,
                json.dumps(provider_response),
                now_iso(),
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


@app.on_event("startup")
def startup() -> None:
    if not settings.relay_secret:
        raise RuntimeError("IMESSAGE_RELAY_SECRET is required")
    init_db()


@app.get("/health")
def health() -> dict:
    init_db()
    return {"status": "ok", "service": "puregamma-imessage-relay", "os": platform.system(), "secret_configured": bool(settings.relay_secret)}


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
    duplicate = existing_delivery(payload.idempotency_key)
    if duplicate:
        return duplicate
    provider_response = send_via_messages_app(payload.recipient, payload.message)
    status = provider_response["status"]
    record_delivery(payload.idempotency_key, payload.recipient, payload.message, status, provider_response)
    return {
        "idempotency_key": payload.idempotency_key,
        "recipient": payload.recipient,
        "status": status,
        "provider_response": provider_response,
        "duplicate": False,
    }
