from __future__ import annotations

"""Photon iMessage provider unit tests.

Covers provider selection, the HTTP contract (URL, bearer auth, payloads,
Idempotency-Key, timeouts), success/permanent/retryable result mapping,
response sanitization and missing-configuration behavior.
"""
import base64
import io
import json
import urllib.error
from types import SimpleNamespace

from apps.api.config import Settings
from packages.notifications.dispatcher import NotificationDispatcher
from packages.notifications.imessage.photon_provider import PhotonIMessageProvider
from packages.notifications.imessage.provider_factory import get_imessage_provider


def _settings(**overrides) -> SimpleNamespace:
    values = dict(
        photon_api_key="photon-key",
        photon_line_id="+14243825596",
        photon_http_proxy_url="https://proxy.example",
        photon_server_url="https://server.example",
        photon_webhook_secret="webhook-secret",
        photon_request_timeout_seconds=5,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeResponse:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install_fake_urlopen(monkeypatch, handler):
    import packages.notifications.imessage.photon_provider as pp

    monkeypatch.setattr(pp.urllib.request, "urlopen", handler)


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def test_factory_selects_photon_provider():
    settings = Settings(imessage_provider="photon")
    assert isinstance(get_imessage_provider(settings), PhotonIMessageProvider)


def test_factory_selects_macos_relay_provider():
    from packages.notifications.imessage.macos_relay_client import MacOSIMessageRelayClient

    settings = Settings(imessage_provider="macos_relay")
    assert isinstance(get_imessage_provider(settings), MacOSIMessageRelayClient)


def test_factory_selects_mock_provider_outside_production():
    from packages.notifications.imessage.mock_provider import MockIMessageProvider

    settings = Settings(imessage_provider="mock", app_environment="development")
    assert isinstance(get_imessage_provider(settings), MockIMessageProvider)


def test_factory_rejects_unavailable_provider():
    settings = Settings(imessage_provider="disabled", app_environment="development")
    try:
        get_imessage_provider(settings)
    except RuntimeError as exc:
        assert str(exc) == "IMESSAGE_PROVIDER_UNAVAILABLE"
    else:
        raise AssertionError("expected RuntimeError")


def test_dispatcher_selects_photon_provider(monkeypatch):
    monkeypatch.setattr(
        "packages.notifications.dispatcher.get_settings",
        lambda: Settings(imessage_provider="photon"),
    )
    provider = NotificationDispatcher()._provider("imessage")
    assert isinstance(provider, PhotonIMessageProvider)


# ---------------------------------------------------------------------------
# Text send contract
# ---------------------------------------------------------------------------


def test_send_message_contract_and_sanitization(monkeypatch):
    calls: list[tuple] = []

    def fake_urlopen(request, timeout=None):
        calls.append((request, timeout))
        return FakeResponse(200, {"ok": True, "to": "+15555550100", "text": "hello world", "message_id": "m1"})

    _install_fake_urlopen(monkeypatch, fake_urlopen)
    provider = PhotonIMessageProvider(settings=_settings())
    result = provider.send_message("+15555550100", "hello world", "pg-key-1")

    assert result.ok
    request, timeout = calls[0]
    assert request.full_url == "https://proxy.example/send"
    assert timeout == 5
    assert request.get_header("Idempotency-key") == "pg-key-1"
    expected_token = base64.b64encode(b"https://server.example|photon-key").decode()
    assert request.get_header("Authorization") == f"Bearer {expected_token}"
    assert json.loads(request.data.decode()) == {"to": "+15555550100", "text": "hello world"}
    # The persisted response must never contain the recipient or the body.
    assert "to" not in result.response
    assert "text" not in result.response
    assert result.response["ok"] is True


def test_send_message_maps_validation_error_to_permanent_failure(monkeypatch):
    def fake_urlopen(request, timeout=None):
        fp = io.BytesIO(json.dumps({"ok": False, "error": {"code": "VALIDATION_ERROR"}}).encode())
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", None, fp)

    _install_fake_urlopen(monkeypatch, fake_urlopen)
    result = PhotonIMessageProvider(settings=_settings()).send_message("+15555550100", "hi", "pg-key-2")
    assert not result.ok
    assert result.response["status"] == "invalid_recipient"
    assert result.response["error"] == "VALIDATION_ERROR"


def test_send_message_maps_invalid_recipient_code_to_permanent_failure(monkeypatch):
    def fake_urlopen(request, timeout=None):
        fp = io.BytesIO(json.dumps({"ok": False, "error": {"code": "INVALID_RECIPIENT"}}).encode())
        raise urllib.error.HTTPError(request.full_url, 422, "Unprocessable", None, fp)

    _install_fake_urlopen(monkeypatch, fake_urlopen)
    result = PhotonIMessageProvider(settings=_settings()).send_message("bad", "hi", "pg-key-3")
    assert not result.ok
    assert result.response["status"] == "invalid_recipient"


def test_send_message_maps_5xx_to_retryable_with_backoff(monkeypatch):
    calls: list = []
    sleeps: list = []
    monkeypatch.setattr("packages.notifications.imessage.photon_provider.time.sleep", lambda s: sleeps.append(s))

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        fp = io.BytesIO(json.dumps({"ok": False, "error": {"code": "UPSTREAM_ERROR"}}).encode())
        raise urllib.error.HTTPError(request.full_url, 502, "Bad Gateway", None, fp)

    _install_fake_urlopen(monkeypatch, fake_urlopen)
    result = PhotonIMessageProvider(settings=_settings()).send_message("+15555550100", "hi", "pg-key-4")
    assert not result.ok
    assert result.response["status"] == "failed_retryable"
    assert len(calls) == 3
    assert sleeps == [0.1, 0.2]


def test_send_message_retries_network_failure_then_retryable(monkeypatch):
    calls: list = []
    monkeypatch.setattr("packages.notifications.imessage.photon_provider.time.sleep", lambda s: None)

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        raise TimeoutError("timed out")

    _install_fake_urlopen(monkeypatch, fake_urlopen)
    result = PhotonIMessageProvider(settings=_settings()).send_message("+15555550100", "hi", "pg-key-5")
    assert not result.ok
    assert result.response["status"] == "failed_retryable"
    assert len(calls) == 3


def test_send_message_missing_configuration_returns_clear_error():
    provider = PhotonIMessageProvider(settings=_settings(photon_api_key="", photon_server_url="", photon_http_proxy_url=""))
    result = provider.send_message("+15555550100", "hi", "pg-key-6")
    assert not result.ok
    assert result.response["error"] == "missing_photon_configuration"
    assert set(result.response["missing"]) == {"PHOTON_API_KEY", "PHOTON_SERVER_URL", "PHOTON_HTTP_PROXY_URL"}


# ---------------------------------------------------------------------------
# Media send contract
# ---------------------------------------------------------------------------


def test_send_media_multipart_audio(monkeypatch):
    calls: list[tuple] = []

    def fake_urlopen(request, timeout=None):
        calls.append((request, timeout))
        return FakeResponse(200, {"ok": True, "message_id": "m2"})

    _install_fake_urlopen(monkeypatch, fake_urlopen)
    provider = PhotonIMessageProvider(settings=_settings())
    result = provider.send_media("+15555550100", b"\x00\x01audio", filename="Voice Note", kind="audio", idempotency_key="pg-media-1")

    assert result.ok
    request, timeout = calls[0]
    assert request.full_url == "https://proxy.example/send/file"
    assert timeout == 30  # media uses max(3x timeout, 30)
    assert request.get_header("Idempotency-key") == "pg-media-1"
    content_type = request.get_header("Content-type")
    assert content_type.startswith("multipart/form-data; boundary=")
    body = request.data
    assert b'name="to"' in body
    assert b"+15555550100" in body
    assert b'name="file"; filename="Voice Note"' in body
    assert b"\x00\x01audio" in body
    assert b'name="audio"' in body
    assert b"true" in body
    assert "message_id" in result.response
    assert result.response["ok"] is True


def test_send_media_file_omits_audio_flag(monkeypatch):
    calls: list = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        return FakeResponse(200, {"ok": True})

    _install_fake_urlopen(monkeypatch, fake_urlopen)
    provider = PhotonIMessageProvider(settings=_settings())
    result = provider.send_media("+15555550100", b"pdf-bytes", filename="report.pdf", kind="file", idempotency_key="pg-media-2")
    assert result.ok
    body = calls[0].data
    assert b'name="file"; filename="report.pdf"' in body
    assert b'name="audio"' not in body


def test_send_media_missing_configuration_returns_clear_error():
    provider = PhotonIMessageProvider(settings=_settings(photon_api_key=""))
    result = provider.send_media("+15555550100", b"x", filename="a.mp3", kind="audio", idempotency_key="pg-media-3")
    assert not result.ok
    assert result.response["error"] == "missing_photon_configuration"
