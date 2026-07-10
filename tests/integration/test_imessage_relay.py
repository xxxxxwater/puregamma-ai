from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


def load_relay_module():
    relay_dir = Path(__file__).resolve().parents[2] / "apps" / "imessage-relay"
    if str(relay_dir) not in sys.path:
        sys.path.insert(0, str(relay_dir))
    spec = importlib.util.spec_from_file_location("puregamma_imessage_relay", relay_dir / "relay.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_imessage_relay_accepts_valid_hmac_and_dedupes(tmp_path, monkeypatch):
    relay = load_relay_module()
    monkeypatch.setattr(
        relay,
        "settings",
        SimpleNamespace(
            relay_secret="secret",
            db_path=str(tmp_path / "relay.sqlite3"),
            max_message_length=3000,
            replay_tolerance_seconds=300,
            applescript_path="/tmp/missing.applescript",
        ),
    )
    monkeypatch.setattr(relay, "send_via_messages_app", lambda recipient, message: {"ok": True, "status": "sent"})
    body = json.dumps({"recipient": "+15555550100", "message": "hello", "idempotency_key": "relay-1"}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = relay.compute_hmac("secret", timestamp, body)

    with TestClient(relay.app) as client:
        first = client.post("/send", content=body, headers={"X-PG-Timestamp": timestamp, "X-PG-Signature": signature, "X-PG-Idempotency-Key": "relay-1"})
        second = client.post("/send", content=body, headers={"X-PG-Timestamp": timestamp, "X-PG-Signature": signature, "X-PG-Idempotency-Key": "relay-1"})

    assert first.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.status_code == 200
    assert second.json()["duplicate"] is True


def test_imessage_relay_rejects_invalid_hmac(tmp_path, monkeypatch):
    relay = load_relay_module()
    monkeypatch.setattr(
        relay,
        "settings",
        SimpleNamespace(
            relay_secret="secret",
            db_path=str(tmp_path / "relay.sqlite3"),
            max_message_length=3000,
            replay_tolerance_seconds=300,
            applescript_path="/tmp/missing.applescript",
        ),
    )
    body = json.dumps({"recipient": "+15555550100", "message": "hello", "idempotency_key": "relay-bad"}, separators=(",", ":")).encode()

    with TestClient(relay.app) as client:
        response = client.post("/send", content=body, headers={"X-PG-Timestamp": str(int(time.time())), "X-PG-Signature": "bad"})

    assert response.status_code == 401


def test_imessage_relay_rejects_timestamp_replay(tmp_path, monkeypatch):
    relay = load_relay_module()
    monkeypatch.setattr(
        relay,
        "settings",
        SimpleNamespace(
            relay_secret="secret",
            db_path=str(tmp_path / "relay.sqlite3"),
            max_message_length=3000,
            replay_tolerance_seconds=1,
            applescript_path="/tmp/missing.applescript",
        ),
    )
    body = json.dumps({"recipient": "+15555550100", "message": "hello", "idempotency_key": "relay-old"}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()) - 10)
    signature = relay.compute_hmac("secret", timestamp, body)

    with TestClient(relay.app) as client:
        response = client.post("/send", content=body, headers={"X-PG-Timestamp": timestamp, "X-PG-Signature": signature})

    assert response.status_code == 401
