from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from config import settings
from inbound import inbound_loop, init_inbound_state


class SendRequest(BaseModel):
    recipient: str
    message: str
    idempotency_key: str


class SendMediaRequest(BaseModel):
    recipient: str
    file_base64: str
    filename: str = "Audio Message"
    kind: str = "audio"  # "audio" renders as an iMessage voice bubble; "file" sends a plain attachment
    idempotency_key: str


# iMessage voice bubbles are CAF containers with Opus audio at 24 kHz mono,
# transferred under the name "Audio Message.caf" (verified against chat.db
# records of real audio messages: uti=com.apple.coreaudio-format,
# is_audio_message=1). Plain .mp3/.m4a attachments never render as voice
# bubbles, so audio payloads are transcoded on-device with afconvert.
VOICE_BUBBLE_FILENAME = "Audio Message.caf"
_AFCONVERT_TIMEOUT_SECONDS = 60


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


def _prepare_media(file_base64: str, filename: str, kind: str, work_key: str) -> dict:
    """Decode, optionally transcode to the iMessage voice-bubble format, and
    return the on-disk path plus display metadata. Caller must clean up."""
    data = base64.b64decode(file_base64, validate=True)
    if not data:
        raise ValueError("empty_media")
    if len(data) > settings.max_media_bytes:
        raise ValueError("media_too_large")
    work_dir = os.path.join(settings.media_work_dir, hashlib.sha256(work_key.encode()).hexdigest()[:24])
    os.makedirs(work_dir, exist_ok=True)
    if kind == "audio":
        source_path = os.path.join(work_dir, "source.audio")
        with open(source_path, "wb") as handle:
            handle.write(data)
        target_path = os.path.join(work_dir, VOICE_BUBBLE_FILENAME)
        if platform.system() == "Darwin":
            completed = subprocess.run(
                ["afconvert", "-f", "caff", "-d", "opus@24000", "-c", "1", source_path, target_path],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=_AFCONVERT_TIMEOUT_SECONDS,
            )
            if completed.returncode != 0 or not os.path.exists(target_path):
                raise RuntimeError(f"afconvert_failed:{completed.stderr.strip()[:200]}")
        else:
            with open(target_path, "wb") as handle:
                handle.write(data)
        return {"path": target_path, "display_name": VOICE_BUBBLE_FILENAME, "transcoded": platform.system() == "Darwin"}
    safe_name = re.sub(r"[^\w. -]", "_", os.path.basename(filename or "attachment"))[:120] or "attachment"
    target_path = os.path.join(work_dir, safe_name)
    with open(target_path, "wb") as handle:
        handle.write(data)
    return {"path": target_path, "display_name": safe_name, "transcoded": False}


def _cleanup_media(path: str) -> None:
    shutil.rmtree(os.path.dirname(path), ignore_errors=True)


def send_file_via_messages_app(recipient: str, path: str) -> dict:
    if platform.system() != "Darwin":
        return {"ok": False, "status": "unsupported_os"}
    if not os.path.exists(settings.applescript_file_path):
        return {"ok": False, "status": "missing_applescript"}
    completed = subprocess.run(
        ["osascript", settings.applescript_file_path, recipient, path],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if completed.returncode != 0:
        return {"ok": False, "status": "failed", "stderr": completed.stderr.strip()}
    return {"ok": True, "status": "sent", "stdout": completed.stdout.strip()}


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


def _send_inbound_reply(recipient: str, message: str, idempotency_key: str) -> dict:
    duplicate = existing_delivery(idempotency_key)
    if duplicate and duplicate["status"] == "sent":
        return duplicate
    provider_response = send_via_messages_app(recipient, message[:settings.max_message_length])
    status = "sent" if provider_response.get("ok") else "failed_retryable"
    record_delivery(
        idempotency_key,
        recipient,
        message,
        status,
        {"ok": provider_response.get("ok", False), "status": provider_response.get("status")},
        1,
        None,
        None if status == "sent" else str(provider_response.get("status")),
    )
    return provider_response


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.relay_secret:
        raise RuntimeError("IMESSAGE_RELAY_SECRET is required")
    init_db()
    init_inbound_state()
    thread = threading.Thread(
        target=lambda: asyncio.run(inbound_loop(_send_inbound_reply)),
        name="puregamma-imessage-inbound",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        pass


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
    if not re.fullmatch(r"(?:\+[1-9]\d{7,14}|[^\s@]+@[^\s@]+\.[^\s@]+)", payload.recipient):
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


@app.post("/send-media")
async def send_media(
    request: Request,
    x_pg_timestamp: str | None = Header(default=None, alias="X-PG-Timestamp"),
    x_pg_signature: str | None = Header(default=None, alias="X-PG-Signature"),
    x_pg_idempotency_key: str | None = Header(default=None, alias="X-PG-Idempotency-Key"),
) -> dict:
    init_db()
    body = await request.body()
    if not verify_signature(x_pg_timestamp, x_pg_signature, body):
        raise HTTPException(status_code=401, detail="invalid_hmac_signature")
    payload = SendMediaRequest(**json.loads(body.decode()))
    if x_pg_idempotency_key and x_pg_idempotency_key != payload.idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key_mismatch")
    if payload.kind not in {"audio", "file"}:
        raise HTTPException(status_code=400, detail="invalid_kind")
    if not re.fullmatch(r"(?:\+[1-9]\d{7,14}|[^\s@]+@[^\s@]+\.[^\s@]+)", payload.recipient):
        raise HTTPException(status_code=400, detail="invalid_recipient")
    duplicate = existing_delivery(payload.idempotency_key)
    if duplicate and duplicate["status"] == "sent":
        return duplicate
    if duplicate and duplicate["status"] == "failed_retryable" and duplicate.get("next_retry_at") and datetime.fromisoformat(duplicate["next_retry_at"]) > datetime.now(timezone.utc):
        return duplicate
    attempt_count = int(duplicate.get("attempt_count", 0) if duplicate else 0) + 1
    prepared = None
    try:
        prepared = _prepare_media(payload.file_base64, payload.filename, payload.kind, payload.idempotency_key)
    except ValueError as exc:
        detail = str(exc)
        if detail == "invalid_base64":
            raise HTTPException(status_code=400, detail="invalid_base64")
        if detail == "media_too_large":
            raise HTTPException(status_code=400, detail="media_too_large")
        raise HTTPException(status_code=400, detail="empty_media")
    except (binascii.Error, RuntimeError, subprocess.TimeoutExpired) as exc:
        record_delivery(payload.idempotency_key, payload.recipient, f"media:{payload.kind}:{payload.filename}", "failed_permanent", {"ok": False, "status": "transcode_failed"}, attempt_count, None, str(exc)[:300])
        raise HTTPException(status_code=422, detail="media_transcode_failed")
    provider_response = send_file_via_messages_app(payload.recipient, prepared["path"])
    _cleanup_media(prepared["path"])
    raw_status = provider_response["status"]
    permanent = raw_status in {"unsupported_os", "missing_applescript", "invalid_recipient"}
    status = "sent" if provider_response.get("ok") else "failed_permanent" if permanent or attempt_count >= 3 else "failed_retryable"
    delays = (1, 5, 30)
    next_retry_at = (datetime.now(timezone.utc) + timedelta(minutes=delays[min(attempt_count - 1, 2)])).isoformat() if status == "failed_retryable" else None
    record_delivery(payload.idempotency_key, payload.recipient, f"media:{payload.kind}:{prepared['display_name']}", status, {"ok": provider_response.get("ok", False), "status": raw_status}, attempt_count, next_retry_at, None if status == "sent" else raw_status)
    return {
        "idempotency_key": payload.idempotency_key,
        "recipient": payload.recipient,
        "status": status,
        "media": {"kind": payload.kind, "display_name": prepared["display_name"], "transcoded": prepared["transcoded"]},
        "provider_response": {"ok": provider_response.get("ok", False), "status": raw_status},
        "attempt_count": attempt_count,
        "next_retry_at": next_retry_at,
        "duplicate": False,
    }
