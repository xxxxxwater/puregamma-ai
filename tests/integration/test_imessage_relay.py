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


def test_imessage_relay_retries_failed_delivery_after_backoff(tmp_path, monkeypatch):
    relay = load_relay_module()
    monkeypatch.setattr(relay, "settings", SimpleNamespace(relay_secret="secret", db_path=str(tmp_path / "relay.sqlite3"), max_message_length=3000, replay_tolerance_seconds=300, applescript_path="/tmp/send.applescript"))
    outcomes = iter([{"ok": False, "status": "timeout"}, {"ok": True, "status": "sent"}])
    monkeypatch.setattr(relay, "send_via_messages_app", lambda recipient, message: next(outcomes))
    body = json.dumps({"recipient": "+15555550100", "message": "hello", "idempotency_key": "relay-retry"}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = relay.compute_hmac("secret", timestamp, body)
    headers = {"X-PG-Timestamp": timestamp, "X-PG-Signature": signature, "X-PG-Idempotency-Key": "relay-retry"}

    with TestClient(relay.app) as client:
        first = client.post("/send", content=body, headers=headers)
        with relay.sqlite3.connect(relay.settings.db_path) as conn:
            conn.execute("UPDATE deliveries SET next_retry_at = ? WHERE idempotency_key = ?", ((relay.datetime.now(relay.timezone.utc) - relay.timedelta(seconds=1)).isoformat(), "relay-retry"))
        second = client.post("/send", content=body, headers=headers)

    assert first.json()["status"] == "failed_retryable"
    assert second.json()["status"] == "sent"
    assert second.json()["attempt_count"] == 2


def _media_settings(tmp_path):
    return SimpleNamespace(
        relay_secret="secret",
        db_path=str(tmp_path / "relay.sqlite3"),
        max_message_length=3000,
        replay_tolerance_seconds=300,
        applescript_path="/tmp/send.applescript",
        applescript_file_path="/tmp/send-file.applescript",
        media_work_dir=str(tmp_path / "media"),
        max_media_bytes=8 * 1024 * 1024,
    )


def test_imessage_relay_send_media_audio_produces_voice_bubble_name(tmp_path, monkeypatch):
    import base64

    relay = load_relay_module()
    monkeypatch.setattr(relay, "settings", _media_settings(tmp_path))
    sent = {}
    monkeypatch.setattr(relay, "send_file_via_messages_app", lambda recipient, path: sent.update(recipient=recipient, path=path) or {"ok": True, "status": "sent"})
    payload = {
        "recipient": "+15555550100",
        "file_base64": base64.b64encode(b"ID3 fake mp3 bytes").decode(),
        "filename": "secretary-reply.mp3",
        "kind": "audio",
        "idempotency_key": "media-1",
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = relay.compute_hmac("secret", timestamp, body)
    headers = {"X-PG-Timestamp": timestamp, "X-PG-Signature": signature, "X-PG-Idempotency-Key": "media-1"}

    with TestClient(relay.app) as client:
        response = client.post("/send-media", content=body, headers=headers)
        duplicate = client.post("/send-media", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert response.json()["media"]["display_name"] == relay.VOICE_BUBBLE_FILENAME
    assert sent["path"].endswith(relay.VOICE_BUBBLE_FILENAME)
    assert duplicate.json()["duplicate"] is True


def test_imessage_relay_send_media_file_keeps_filename(tmp_path, monkeypatch):
    import base64

    relay = load_relay_module()
    monkeypatch.setattr(relay, "settings", _media_settings(tmp_path))
    sent = {}
    monkeypatch.setattr(relay, "send_file_via_messages_app", lambda recipient, path: sent.update(path=path) or {"ok": True, "status": "sent"})
    payload = {
        "recipient": "+15555550100",
        "file_base64": base64.b64encode(b"pdf bytes").decode(),
        "filename": "report.pdf",
        "kind": "file",
        "idempotency_key": "media-2",
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = relay.compute_hmac("secret", timestamp, body)

    with TestClient(relay.app) as client:
        response = client.post("/send-media", content=body, headers={"X-PG-Timestamp": timestamp, "X-PG-Signature": signature})

    assert response.status_code == 200
    assert response.json()["media"]["display_name"] == "report.pdf"
    assert sent["path"].endswith("report.pdf")


def test_imessage_relay_send_media_rejects_bad_input(tmp_path, monkeypatch):
    relay = load_relay_module()
    monkeypatch.setattr(relay, "settings", _media_settings(tmp_path))

    def _signed(payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        return body, {"X-PG-Timestamp": timestamp, "X-PG-Signature": relay.compute_hmac("secret", timestamp, body)}

    with TestClient(relay.app) as client:
        body, headers = _signed({"recipient": "+15555550100", "file_base64": "!!!not-base64!!!", "kind": "audio", "idempotency_key": "media-3"})
        assert client.post("/send-media", content=body, headers=headers).status_code == 400
        body, headers = _signed({"recipient": "+15555550100", "file_base64": "aGk=", "kind": "video", "idempotency_key": "media-4"})
        assert client.post("/send-media", content=body, headers=headers).status_code == 400
        body, headers = _signed({"recipient": "not-a-number", "file_base64": "aGk=", "kind": "audio", "idempotency_key": "media-5"})
        assert client.post("/send-media", content=body, headers=headers).status_code == 400
