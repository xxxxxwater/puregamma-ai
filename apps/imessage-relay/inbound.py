from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

from config import settings


def _signature(timestamp: str, body: bytes) -> str:
    return hmac.new(
        settings.relay_secret.encode(),
        timestamp.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()


def init_inbound_state() -> None:
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inbound_events (
                message_rowid INTEGER PRIMARY KEY,
                sender_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inbound_state (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


def _heartbeat(value: str) -> None:
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            "INSERT INTO inbound_state(name, value) VALUES ('inbound_heartbeat', ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (value,),
        )


def _chat_db_path() -> Path:
    return Path.home() / "Library" / "Messages" / "chat.db"


def _state(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM inbound_state WHERE name = 'last_rowid'").fetchone()
    return int(row[0]) if row else None


def _set_state(conn: sqlite3.Connection, rowid: int) -> None:
    conn.execute(
        "INSERT INTO inbound_state(name, value) VALUES ('last_rowid', ?) "
        "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
        (str(rowid),),
    )


def _message_text(plain_text: str | None, attributed_body: bytes | None) -> str:
    if plain_text and plain_text.strip():
        return plain_text.strip()
    if not attributed_body:
        return ""
    marker = b"NSString\x01\x94\x01"
    start = attributed_body.find(marker)
    if start < 0:
        return ""
    payload = attributed_body[start + len(marker):]
    if len(payload) < 2:
        return ""
    length = payload[1]
    value = payload[2:2 + length]
    try:
        return value.decode("utf-8").strip()
    except UnicodeDecodeError:
        return ""


def _new_messages() -> list[tuple[int, str, str]]:
    chat_db = _chat_db_path()
    if not chat_db.exists():
        return []
    with sqlite3.connect(settings.db_path) as relay_conn:
        watermark = _state(relay_conn)
        with sqlite3.connect(f"file:{chat_db}?mode=ro", uri=True) as messages_conn:
            latest = messages_conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM message").fetchone()[0]
            if watermark is None:
                _set_state(relay_conn, int(latest))
                return []
            rows = messages_conn.execute(
                """
                SELECT message.rowid, handle.id, message.text, message.attributedBody
                FROM message
                JOIN handle ON handle.rowid = message.handle_id
                WHERE message.rowid > ?
                  AND message.is_from_me = 0
                  AND message.service = 'iMessage'
                ORDER BY message.rowid ASC
                """,
                (watermark,),
            ).fetchall()
        _set_state(relay_conn, int(latest))
    return [
        (int(rowid), str(sender), text)
        for rowid, sender, plain_text, attributed_body in rows
        if (text := _message_text(plain_text, attributed_body))
    ]


def _post_inbound(message_rowid: int, sender: str, text: str) -> dict:
    body = json.dumps(
        {"message_id": str(message_rowid), "sender": sender, "content": text[:3000]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(time.time()))
    request = urllib.request.Request(
        f"{settings.agent_api_url}/internal/imessage/inbound",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-PG-Timestamp": timestamp,
            "X-PG-Signature": _signature(timestamp, body),
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode())


def _record(message_rowid: int, sender: str, status: str, error: str | None = None) -> None:
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO inbound_events(message_rowid, sender_hash, status, created_at, last_error) "
            "VALUES (?, ?, ?, datetime('now'), ?)",
            (message_rowid, hashlib.sha256(sender.encode()).hexdigest(), status, error),
        )


async def inbound_loop(send_reply) -> None:
    init_inbound_state()
    _heartbeat(str(int(time.time())))
    while True:
        try:
            for message_rowid, sender, content in _new_messages():
                try:
                    result = await asyncio.to_thread(_post_inbound, message_rowid, sender, content)
                    reply = str(result.get("reply") or "").strip()
                    if reply:
                        await asyncio.to_thread(send_reply, sender, reply, f"inbound-reply-{message_rowid}")
                    _record(message_rowid, sender, "completed")
                except (OSError, sqlite3.Error, urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
                    _record(message_rowid, sender, "failed", str(exc)[:500])
        except (OSError, sqlite3.Error) as exc:
            _heartbeat(f"error:{str(exc)[:300]}")
        await asyncio.sleep(max(1.0, settings.agent_poll_seconds))
