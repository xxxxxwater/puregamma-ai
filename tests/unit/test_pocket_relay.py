from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

RELAY_DIR = str(Path(__file__).resolve().parents[2] / "apps" / "pocket-relay")


@pytest.fixture()
def client():
    os.environ["POCKET_STATE_DIR"] = tempfile.mkdtemp(prefix="pg-pocket-test-")
    os.environ["POCKET_WEB_TARGET"] = "http://127.0.0.1:9"
    os.environ["POCKET_RPC_SECRET"] = "testsecret"
    if RELAY_DIR not in sys.path:
        sys.path.insert(0, RELAY_DIR)
    # 每次全新导入，避免模块缓存串状态
    for module in ("config", "pin", "tunnel", "qr", "main"):
        sys.modules.pop(module, None)
    from fastapi.testclient import TestClient
    from main import app
    yield TestClient(app)
    for module in ("config", "pin", "tunnel", "qr", "main"):
        sys.modules.pop(module, None)


H = {"x-pocket-rpc-token": "testsecret"}


def test_health_and_rpc_status(client):
    assert client.get("/health").status_code == 200
    body = client.get("/rpc/status", headers=H).json()
    assert len(body["lan"]["pin"]) == 8
    assert len(body["public"]["pin"]) == 8
    assert body["lan"]["pin"] != body["public"]["pin"]
    assert body["public"]["running"] is False


def test_proxy_requires_pin(client):
    assert client.get("/").status_code == 401
    body = client.get("/rpc/status", headers=H).json()
    response = client.get(f"/?pin={body['lan']['pin']}")
    # 上游不可达 → 502/503，但必须越过 401 门禁
    assert response.status_code in {502, 503}
    gate = client.get("/", headers={"accept": "text/html"})
    assert gate.status_code == 401
    assert "访问验证" in gate.text


def test_pin_rotate_and_custom(client):
    before = client.get("/rpc/status", headers=H).json()["lan"]["pin"]
    rotated = client.post("/rpc/pin/rotate", json={"which": "lan"}, headers=H).json()["lan"]
    assert len(rotated) == 8
    assert rotated != before
    assert client.post("/rpc/pin/custom", json={"which": "public", "pin": "12345678"}, headers=H).json() == {"public": "12345678"}
    assert client.post("/rpc/pin/custom", json={"which": "public", "pin": "abc"}, headers=H).status_code == 400


def test_rpc_secret_enforced(client):
    assert client.get("/rpc/status").status_code == 403
    assert client.get("/rpc/status", headers={"x-pocket-rpc-token": "wrong"}).status_code == 403


def test_qr_and_control_page(client):
    qr = client.get("/rpc/qr?kind=lan", headers=H)
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    page = client.get("/_pocket")
    assert page.status_code == 200
    assert "手机访问" in page.text
