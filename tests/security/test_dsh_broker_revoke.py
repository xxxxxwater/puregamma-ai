"""Logout → DSH session broker revoke notification.

Pins: off by default (and while DSH multi-tenancy is off); when configured,
logout posts only the user id with the broker secret, after the response;
a broker failure never breaks logout; the wire format matches the broker's
``POST /__broker/revoke`` (204 on success).
"""
from __future__ import annotations

import dataclasses
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from apps.api.config import get_settings, validate_production_settings
from apps.api.services import dsh_broker
from tests.conftest import auth_headers
from tests.security.test_production_configuration import valid_production_settings

SECRET = "s" * 40


@pytest.fixture()
def calls(monkeypatch):
    recorded: list[dict] = []

    class Response:
        status_code = 204

    def fake_post(url, **kwargs):
        recorded.append({"url": url, **kwargs})
        return Response()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    return recorded


def configure(monkeypatch, **overrides):
    settings = dataclasses.replace(get_settings(), **overrides)
    monkeypatch.setattr("apps.api.services.dsh_broker.get_settings", lambda: settings)
    return settings


def test_logout_does_not_notify_by_default(api_client, normal_user, calls):
    assert get_settings().dsh_broker_revoke_url == ""
    assert api_client.post("/auth/logout", headers=auth_headers(normal_user)).status_code == 200
    assert calls == []


def test_revoke_url_alone_is_inert_while_multi_tenancy_is_off(api_client, normal_user, calls, monkeypatch):
    configure(monkeypatch, dsh_broker_revoke_url="http://127.0.0.1:3480/__broker/revoke", dsh_broker_secret=SECRET)
    assert api_client.post("/auth/logout", headers=auth_headers(normal_user)).status_code == 200
    assert calls == []


def test_logout_notifies_the_broker_with_only_the_user_id(api_client, normal_user, calls, monkeypatch):
    configure(monkeypatch, dsh_multi_tenant_enabled=True, dsh_broker_secret=SECRET, dsh_broker_revoke_url="http://127.0.0.1:3480/__broker/revoke")
    headers = auth_headers(normal_user)
    assert api_client.post("/auth/logout", headers=headers).status_code == 200
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "http://127.0.0.1:3480/__broker/revoke"
    assert call["json"] == {"user_id": normal_user.id}
    assert call["headers"] == {"X-PureGamma-Broker-Secret": SECRET}
    assert call["timeout"] <= 2.0
    assert call["follow_redirects"] is False
    # The session itself is revoked regardless.
    assert api_client.get("/me", headers=headers).status_code == 401


def test_a_broker_failure_never_breaks_logout(api_client, normal_user, monkeypatch):
    configure(monkeypatch, dsh_multi_tenant_enabled=True, dsh_broker_secret=SECRET, dsh_broker_revoke_url="http://127.0.0.1:9/__broker/revoke")
    import httpx

    def boom(*_args, **_kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", boom)
    headers = auth_headers(normal_user)
    assert api_client.post("/auth/logout", headers=headers).status_code == 200
    assert api_client.get("/me", headers=headers).status_code == 401
    assert dsh_broker.notify_broker_logout(normal_user.id) is False


def test_wire_format_against_a_local_broker_stub(monkeypatch):
    received: list[tuple[str, dict, dict]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((self.path, dict(self.headers), body))
            ok = self.headers.get("X-PureGamma-Broker-Secret") == SECRET
            self.send_response(204 if ok else 403)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/__broker/revoke"
        configure(monkeypatch, dsh_multi_tenant_enabled=True, dsh_broker_secret=SECRET, dsh_broker_revoke_url=url)
        assert dsh_broker.notify_broker_logout("user-123") is True
        configure(monkeypatch, dsh_multi_tenant_enabled=True, dsh_broker_secret="w" * 40, dsh_broker_revoke_url=url)
        assert dsh_broker.notify_broker_logout("user-123") is False, "a 403 is a failure"
    finally:
        server.shutdown()
    path, headers, body = received[0]
    assert path == "/__broker/revoke"
    assert body == {"user_id": "user-123"}
    assert headers["Content-Type"] == "application/json"


def test_production_rejects_a_non_http_revoke_url():
    settings = dataclasses.replace(valid_production_settings(), dsh_broker_revoke_url="file:///etc/passwd")
    with pytest.raises(RuntimeError, match="DSH_BROKER_REVOKE_URL"):
        validate_production_settings(settings)
