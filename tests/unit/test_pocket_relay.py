from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

RELAY_DIR = str(Path(__file__).resolve().parents[2] / "apps" / "pocket-relay")
H = {"x-pocket-rpc-token": "testsecret"}
# cloudflared 转发过来的隧道 Host：中继据此选择公网密码 / 公网行为
TUNNEL = {"host": "repro-check.trycloudflare.com", "accept": "text/html"}

SMALL_PAGE = b"<html><body>small page</body></html>"
# 比一次 socket 读大得多：旧实现只在「响应能一口气发完」时才侥幸成功，
# 真实页面（Next.js HTML 约 100KB+）会被截断成 Cloudflare 520。
LARGE_PAGE = b"<html><body>" + b"<p>puregamma page</p>" * 12000 + b"</body></html>"


def _reset_modules() -> None:
    # 每次全新导入，避免模块缓存串状态
    for module in ("config", "pin", "tunnel", "qr", "main"):
        sys.modules.pop(module, None)


def _build_client(monkeypatch, **env):
    """按给定环境变量构建一个全新导入的中继 TestClient。"""
    state_dir = tempfile.mkdtemp(prefix="pg-pocket-test-")
    values = {
        "POCKET_STATE_DIR": state_dir,
        "POCKET_WEB_TARGET": "http://127.0.0.1:9",
        "POCKET_RPC_SECRET": "testsecret",
        "POCKET_APP_ORIGIN": "",
        "POCKET_PUBLIC_HOSTS": "",
    }
    values.update(env)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    if RELAY_DIR not in sys.path:
        sys.path.insert(0, RELAY_DIR)
    _reset_modules()
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app), state_dir


@pytest.fixture()
def client(monkeypatch):
    test_client, _ = _build_client(monkeypatch)
    yield test_client
    _reset_modules()


class _UpstreamHandler(BaseHTTPRequestHandler):
    """最小的真实上游：/large 返回大页面，/echo 回显收到的路径与查询串。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/echo"):
            payload = self.path.encode()
        elif self.path.startswith("/large"):
            payload = LARGE_PAGE
        else:
            payload = SMALL_PAGE
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # pragma: no cover - 静默测试日志
        pass


@pytest.fixture()
def upstream() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _pin(kind: str) -> str:
    import pin

    return pin.get_public_pin() if kind == "public" else pin.get_lan_pin()


def test_health_and_rpc_status(client):
    assert client.get("/health").status_code == 200
    body = client.get("/rpc/status", headers=H).json()
    assert len(body["public"]["pin"]) == 8
    assert body["public"]["running"] is False
    assert body["session"]["restart_requires_relogin"] is True
    # SaaS：局域网段整体下线（云主机没有家庭局域网，本地 IP 链接会暴露服务器地址）
    assert "lan" not in body


def test_proxy_requires_pin(client):
    assert client.get("/").status_code == 401
    gate = client.get("/", headers={"accept": "text/html"})
    assert gate.status_code == 401
    assert "访问验证" in gate.text
    # 非浏览器请求拿到 JSON，而不是密码页
    body = client.get("/api/whatever")
    assert body.status_code == 401
    assert body.json()["detail"] == "PIN required"
    # 本地入口用局域网密码越过门禁；上游不可达时如实返回 502
    response = client.get(f"/?pin={_pin('lan')}")
    assert response.status_code == 502


def test_pin_entry_sets_a_session_cookie(monkeypatch, upstream):
    """回归：PIN 首次通过必须发会话 cookie。

    旧实现里 _authorized() 会先匹配 ?pin= 并直接返回，发 cookie 的分支是死代码，
    手机每个请求都得重新带上 ?pin=，换个链接就掉回密码页。
    """
    test_client, _ = _build_client(monkeypatch, POCKET_WEB_TARGET=upstream)
    first = test_client.get(f"/small?pin={_pin('lan')}", headers={"accept": "text/html"})
    assert first.status_code == 200
    assert first.cookies.get("pg_pocket")
    second = test_client.get("/small", headers={"accept": "text/html"})
    assert second.status_code == 200
    assert second.content == SMALL_PAGE


def test_pin_is_not_forwarded_upstream(monkeypatch, upstream):
    """访问 PIN 不该出现在上游 URL 里（上游日志 / Referer / 跳转 Location 都会带上）。"""
    test_client, _ = _build_client(monkeypatch, POCKET_WEB_TARGET=upstream)
    response = test_client.get(f"/echo?pin={_pin('lan')}&locale=zh", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert response.text == "/echo?locale=zh"


def test_proxy_streams_the_whole_page_body(monkeypatch, upstream):
    """回归：上游客户端必须比请求处理函数活得更久（Cloudflare 520 /「HOST 错误」的根因）。

    每个请求一个 httpx.AsyncClient 时，处理函数返回就把连接关了，而 Starlette 是在
    返回之后才迭代 StreamingResponse 的内容，于是大页面在这里被截断，cloudflared
    只能给手机返回 Cloudflare 的 520 错误页。
    """
    test_client, _ = _build_client(monkeypatch, POCKET_WEB_TARGET=upstream)
    response = test_client.get(f"/large?pin={_pin('lan')}", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert response.content == LARGE_PAGE


def test_tunnel_entry_hands_the_phone_to_the_app_origin(monkeypatch):
    """隧道域名与正式站点不同源，代理整站不可用：PIN 通过后必须把手机送到正式站点。"""
    test_client, _ = _build_client(
        monkeypatch, POCKET_APP_ORIGIN="https://app.puregamma.ai", POCKET_WEB_TARGET="http://127.0.0.1:9"
    )
    gate = test_client.get("/", headers=TUNNEL)
    assert gate.status_code == 401
    assert "访问验证" in gate.text
    assert "正式站点" in gate.text

    entry = test_client.get(f"/zh/dashboard?pin={_pin('public')}", headers=TUNNEL, follow_redirects=False)
    assert entry.status_code == 302
    assert entry.headers["location"] == "https://app.puregamma.ai/zh/dashboard"
    assert entry.cookies.get("pg_pocket")

    # 已有会话 cookie 的访问同样直接送到正式站点，不再在隧道域名上代理
    again = test_client.get("/zh/agent", headers=TUNNEL, follow_redirects=False)
    assert again.status_code == 302
    assert again.headers["location"] == "https://app.puregamma.ai/zh/agent"


def test_tunnel_without_app_origin_still_proxies(monkeypatch, upstream):
    """自托管（未配置正式站点）时保持原有行为：在入口域名上直接代理整站。"""
    test_client, _ = _build_client(monkeypatch, POCKET_WEB_TARGET=upstream)
    response = test_client.get(f"/small?pin={_pin('public')}", headers=TUNNEL)
    assert response.status_code == 200
    assert response.content == SMALL_PAGE


def test_lan_surface_proxies_even_with_app_origin(monkeypatch, upstream):
    """跳转只针对临时隧道域名；局域网/稳定域名入口继续代理。"""
    test_client, _ = _build_client(
        monkeypatch, POCKET_WEB_TARGET=upstream, POCKET_APP_ORIGIN="https://app.puregamma.ai"
    )
    response = test_client.get(f"/small?pin={_pin('lan')}", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert response.content == SMALL_PAGE


def test_pin_rotate_and_custom(client):
    before = client.get("/rpc/status", headers=H).json()["public"]["pin"]
    rotated = client.post("/rpc/pin/rotate", json={"which": "public"}, headers=H).json()["public"]
    assert len(rotated) == 8
    assert rotated != before
    assert client.post("/rpc/pin/custom", json={"which": "public", "pin": "12345678"}, headers=H).json() == {
        "public": "12345678"
    }
    assert client.post("/rpc/pin/custom", json={"which": "public", "pin": "abc"}, headers=H).status_code == 400
    # 自定义密码后不再被轮换覆盖
    assert client.post("/rpc/pin/rotate", json={"which": "public"}, headers=H).json()["public"] == "12345678"


def test_rpc_secret_enforced(client):
    assert client.get("/rpc/status").status_code == 403
    assert client.get("/rpc/status", headers={"x-pocket-rpc-token": "wrong"}).status_code == 403


def test_qr_and_control_page(client, monkeypatch):
    # 隧道没开就没有公网 URL 可编码；LAN 段已下线
    assert client.get("/rpc/qr?kind=public", headers=H).status_code == 400
    assert client.get("/rpc/qr?kind=lan", headers=H).status_code == 400
    import main

    monkeypatch.setattr(
        main.manager,
        "status",
        lambda: {
            "running": True,
            "public_url": "https://repro-check.trycloudflare.com",
            "started_at": 0.0,
            "last_error": None,
        },
    )
    qr = client.get("/rpc/qr?kind=public", headers=H)
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    page = client.get("/_pocket")
    assert page.status_code == 200
    assert "手机访问" in page.text

class _HandoffHandler(BaseHTTPRequestHandler):
    """假的 SaaS 交接接口：记录收到的中继密钥，按 state 返回成功或失败。"""

    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        state = self.server.state  # type: ignore[attr-defined]
        state["token"] = self.headers.get("x-pocket-rpc-token")
        state["language"] = self.headers.get("accept-language")
        length = int(self.headers.get("content-length") or 0)
        if length:
            self.rfile.read(length)
        if state["status"] == 200:
            payload = json.dumps({"handoff_url": state["handoff_url"], "expires_in": 60}).encode()
        else:
            payload = json.dumps({"detail": {"code": "REMOTE_LOGIN_NOT_CONFIGURED"}}).encode()
        self.send_response(state["status"])
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # pragma: no cover - 静默测试日志
        pass


@pytest.fixture()
def handoff_api() -> Iterator[dict]:
    handoff_url = "https://api.puregamma.ai/auth/mobile/web-session/consume?code=stub-code"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HandoffHandler)
    server.state = {"status": 200, "handoff_url": handoff_url, "token": None, "language": None}  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        server.state["endpoint"] = f"http://127.0.0.1:{server.server_address[1]}/api/mobile-access/session-handoff"  # type: ignore[attr-defined]
        yield server.state  # type: ignore[attr-defined]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_tunnel_handoff_mints_a_one_time_login(monkeypatch, handoff_api):
    """配置交接接口后，PIN 通过即给手机一次性登录链接，不再去登录页。"""
    test_client, _ = _build_client(
        monkeypatch,
        POCKET_APP_ORIGIN="https://app.puregamma.ai",
        POCKET_HANDOFF_URL=handoff_api["endpoint"],
        POCKET_RPC_SECRET="relay-secret",
    )
    entry = test_client.get(
        f"/zh?pin={_pin('public')}",
        headers={**TUNNEL, "accept-language": "zh-CN,zh;q=0.9"},
        follow_redirects=False,
    )
    assert entry.status_code == 302
    assert entry.headers["location"] == handoff_api["handoff_url"]
    assert entry.cookies.get("pg_pocket")
    assert handoff_api["token"] == "relay-secret"
    assert handoff_api["language"] == "zh-CN,zh;q=0.9"


def test_handoff_failure_falls_back_to_the_plain_app_redirect(monkeypatch, handoff_api):
    """交接接口不可用时不能让手机卡住：退回原来的「跳到正式站点、自行登录」。"""
    handoff_api["status"] = 503
    test_client, _ = _build_client(
        monkeypatch,
        POCKET_APP_ORIGIN="https://app.puregamma.ai",
        POCKET_HANDOFF_URL=handoff_api["endpoint"],
        POCKET_RPC_SECRET="relay-secret",
    )
    entry = test_client.get(f"/zh/agent?pin={_pin('public')}", headers=TUNNEL, follow_redirects=False)
    assert entry.status_code == 302
    assert entry.headers["location"] == "https://app.puregamma.ai/zh/agent"


def test_handoff_is_skipped_without_the_relay_secret(monkeypatch, handoff_api):
    test_client, _ = _build_client(
        monkeypatch,
        POCKET_APP_ORIGIN="https://app.puregamma.ai",
        POCKET_HANDOFF_URL=handoff_api["endpoint"],
        POCKET_RPC_SECRET="",
    )
    entry = test_client.get(f"/?pin={_pin('public')}", headers=TUNNEL, follow_redirects=False)
    assert entry.status_code == 302
    assert entry.headers["location"] == "https://app.puregamma.ai/"
    assert handoff_api["token"] is None


def test_pin_brute_force_is_rate_limited_per_client(monkeypatch):
    """8 位密码是唯一口令（配上交接就等于账号登录），在线爆破必须被挡住。"""
    test_client, _ = _build_client(monkeypatch)
    attacker = {"accept": "text/html", "cf-connecting-ip": "203.0.113.9"}
    for _ in range(10):
        assert test_client.get("/?pin=00000000", headers=attacker).status_code == 401
    blocked = test_client.get("/?pin=00000000", headers=attacker)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "900"
    assert "尝试次数过多" in blocked.text
    # 锁定期内同一个地址即使输对也被拒；换一个地址立刻恢复
    assert test_client.get(f"/?pin={_pin('lan')}", headers=attacker).status_code == 429
    other = {"accept": "text/html", "cf-connecting-ip": "198.51.100.7"}
    assert test_client.get(f"/?pin={_pin('lan')}", headers=other).status_code == 502


def test_a_paired_phone_survives_attack_noise(monkeypatch, upstream):
    """限速是按地址计的：别人的爆破锁不住已配对的手机。

    攻击者用独立 cookie jar（拿不到配对 cookie），但共用同一个进程状态。
    """
    test_client, _ = _build_client(monkeypatch, POCKET_WEB_TARGET=upstream)
    import main
    from fastapi.testclient import TestClient

    attacker = TestClient(main.app)
    owner = {"accept": "text/html", "cf-connecting-ip": "203.0.113.9"}
    hostile = {"accept": "text/html", "cf-connecting-ip": "198.51.100.7"}

    assert test_client.get(f"/small?pin={_pin('lan')}", headers=owner).status_code == 200

    for _ in range(11):
        attacker.get("/?pin=00000000", headers=hostile)
    assert attacker.get("/?pin=00000000", headers=hostile).status_code == 429

    # 配对 cookie 在限速检查之前生效，主人不受影响
    assert test_client.get("/small", headers=owner).status_code == 200

