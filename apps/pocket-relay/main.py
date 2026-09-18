from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import socket
import threading
import time
from contextlib import asynccontextmanager
from urllib.parse import urlencode, urljoin

import httpx
import websockets.asyncio.client as wsclient
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from pin import (
    get_lan_pin,
    get_public_pin,
    pin_is_custom,
    refresh_lan_pin,
    rotate_public_pin,
    set_custom_pin,
)
from qr import make_qr
from tunnel import TunnelManager, auto_recover, save_auto_start, was_auto_start

# 会话保持：登录 cookie 绑定进程级 session key（服务重启后需重输密码，与 dsh-pocket 一致）
SESSION_KEY = secrets.token_hex(32)
COOKIE_NAME = "pg_pocket"
PIN_PARAM = "pin"
COOKIE_MAX_AGE = settings.session_ttl_days * 86400
RESERVED_PREFIXES = ("/health", "/rpc", "/_pocket")

manager = TunnelManager()

# 上游客户端：必须比请求处理函数活得更久。
#
# 早先的实现给每个请求开一个 `async with httpx.AsyncClient(...)`。函数返回时
# 客户端就被关闭了，而 Starlette 是在处理函数返回之后才迭代 StreamingResponse
# 的内容——连接已经断了，Next.js 的 HTML（约 100KB）只发出去一小截就中断。
# cloudflared 收到被截断的响应，手机看到的是 Cloudflare 520 错误页（页面上有
# 「Host」一行），也就是用户报的「HOST 错误」。小响应（PIN 页、307 跳转）能
# 侥幸发完，所以问题只在真实页面上暴露。
#
# 现在整个进程共用一个连接池客户端，流的生命周期交给 _stream_upstream。
_client_lock = threading.Lock()
_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None
UPSTREAM_TIMEOUT = httpx.Timeout(connect=10, read=120, write=30, pool=10)


def _upstream_client() -> httpx.AsyncClient:
    """返回当前事件循环上的共享客户端（跨事件循环/已关闭时重建）。"""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    with _client_lock:
        if _client is None or _client.is_closed or _client_loop is not loop:
            _client = httpx.AsyncClient(
                timeout=UPSTREAM_TIMEOUT,
                follow_redirects=False,
                trust_env=False,
                limits=httpx.Limits(max_connections=64, max_keepalive_connections=16),
            )
            _client_loop = loop
        return _client


async def _close_upstream_client() -> None:
    global _client, _client_loop
    with _client_lock:
        client, _client, _client_loop = _client, None, None
    if client is not None and not client.is_closed:
        await client.aclose()


async def _stream_upstream(upstream: httpx.Response):
    """转发响应体，结束后把连接还回连接池。"""
    try:
        async for chunk in upstream.aiter_bytes():
            yield chunk
    finally:
        await upstream.aclose()


def _is_tunnel_host(host: str | None) -> bool:
    """临时 quick tunnel 域名：随机分配，与正式站点不同源。"""
    return bool(host and host.endswith("trycloudflare.com"))


def _kind_for_host(host: str | None) -> str:
    """按入口域名选择密码：公网（隧道或已配置的公网域名）用公网密码，其余用局域网密码。"""
    if _is_tunnel_host(host) or (host and host in settings.public_hosts):
        return "public"
    return "lan"


def _pin_for_kind(kind: str) -> str:
    return get_public_pin() if kind == "public" else get_lan_pin()


def _cookie_value(kind: str) -> str:
    return hmac.new(SESSION_KEY.encode(), f"{kind}:{_pin_for_kind(kind)}".encode(), hashlib.sha256).hexdigest()


def _cookie_authorized(cookie: str | None, kind: str) -> bool:
    return bool(cookie and hmac.compare_digest(cookie, _cookie_value(kind)))


def _pin_matches(provided: str, kind: str) -> bool:
    return bool(provided and hmac.compare_digest(provided, _pin_for_kind(kind)))


# ---------- PIN 失败限速 ----------
#
# 8 位密码是唯一的口令；一旦配置了 POCKET_HANDOFF_URL，它等同账号登录凭证，
# 所以必须挡住在线爆破。按客户端地址计数（cloudflared 之后 socket 对端没有
# 意义，取它写入的 CF-Connecting-IP），窗口内失败超限即拒绝，成功即清零。
PIN_FAILURE_LIMIT = 10
PIN_FAILURE_WINDOW_SECONDS = 900
_pin_failures: dict[str, list[float]] = {}
_pin_failures_lock = threading.Lock()


def _client_ip(connection: Request | WebSocket) -> str:
    """HTTP 与 WebSocket 都适用：两者都有 headers 与 client。"""
    for header in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
        value = connection.headers.get(header, "").strip()
        if value:
            return value.split(",")[0].strip()
    return connection.client.host if connection.client else "unknown"


def _prune_locked(ip: str, now: float) -> list[float]:
    """窗口内的失败时间戳（必须在持有 _pin_failures_lock 时调用）。"""
    hits = [at for at in _pin_failures.get(ip, []) if now - at < PIN_FAILURE_WINDOW_SECONDS]
    if hits:
        _pin_failures[ip] = hits
    else:
        _pin_failures.pop(ip, None)
    return hits


def _pin_failures_from(ip: str) -> int:
    now = time.monotonic()
    with _pin_failures_lock:
        return len(_prune_locked(ip, now))


def _record_pin_failure(ip: str) -> int:
    now = time.monotonic()
    with _pin_failures_lock:
        hits = _prune_locked(ip, now)
        hits.append(now)
        _pin_failures[ip] = hits
        return len(hits)


def _clear_pin_failures(ip: str) -> None:
    with _pin_failures_lock:
        _pin_failures.pop(ip, None)


def _throttled_response() -> Response:
    minutes = max(1, PIN_FAILURE_WINDOW_SECONDS // 60)
    body = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>PureGamma AI 访问验证</title></head>'
        '<body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#101216;color:#f5f6f8">'
        '<div style="text-align:center;max-width:22rem">'
        '<h2 style="margin:0 0 12px;font-weight:600">尝试次数过多</h2>'
        f'<p style="color:#a2a4a6;margin:0">密码连续输错，请约 {minutes} 分钟后重试。</p>'
        '</div></body></html>'
    )
    return HTMLResponse(body, status_code=429, headers={"Retry-After": str(PIN_FAILURE_WINDOW_SECONDS)})


async def _mint_handoff_url(request: Request) -> str | None:
    """向 SaaS API 换一次性登录交接链接（PIN 通过后手机直接进账号）。"""
    if not settings.handoff_url or not settings.rpc_secret:
        return None
    headers = {"x-pocket-rpc-token": settings.rpc_secret}
    language = request.headers.get("accept-language")
    if language:
        headers["accept-language"] = language
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=10, write=5, pool=5), trust_env=False
        ) as client:
            response = await client.post(settings.handoff_url, headers=headers)
            if response.status_code != 200:
                return None
            url = str(response.json().get("handoff_url") or "")
    except (httpx.HTTPError, ValueError):
        return None
    return url if url.startswith(("http://", "https://")) else None


async def _app_handoff(request: Request) -> Response | None:
    """公网入口：PIN 通过后把手机交给正式站点，而不是在隧道域名上代理整站。

    隧道是随机 `*.trycloudflare.com` 域名，而正式站点把接口调用发到
    `https://api.puregamma.ai`：从隧道域名出发的预检会被 CORS 拒绝
    （CORS_ORIGINS 只认 https://app.puregamma.ai），会话 cookie 又带着
    `Domain=.puregamma.ai; SameSite=Lax`——在 iOS 上属于第三方 cookie，
    登录永远保持不住。所以隧道域名下代理出来的页面「能看不能用」。
    把浏览器送到正式站点，手机拿到的才是完整可用的 PureGamma。
    """
    if not settings.app_origin:
        return None
    minted = await _mint_handoff_url(request)
    if minted:
        # 手机拿到一次性交接码 → 正式站点直接建立会话，不必再走邮箱/Google 登录
        return RedirectResponse(minted, status_code=302)
    query = _forwarded_query(request)
    target = f"{settings.app_origin}{request.url.path or '/'}"
    if query:
        target += f"?{query}"
    return RedirectResponse(target, status_code=302)


def _ws_authorized(websocket: WebSocket, kind: str) -> bool:
    cookie = websocket.cookies.get(COOKIE_NAME)
    if cookie and hmac.compare_digest(cookie, _cookie_value(kind)):
        return True
    return _pin_matches(websocket.query_params.get(PIN_PARAM, ""), kind)


def _private_ok(ip: str) -> bool:
    # 过滤 127.x、docker 内网段（172.16-31.x）、CGNAT/Tailscale（100.64-127.x）与
    # 链路本地（169.254.x）；保留常见的家用/云主机 LAN 段（10.x、192.168.x、172.x 之外的私网）
    parts = [int(part) for part in ip.split(".")[:2] if part.isdigit()]
    if len(parts) < 2:
        return False
    first, second = parts
    if first == 127 or first == 169 or first == 0:
        return False
    if first == 172 and 16 <= second <= 31:
        return False
    if first == 100 and 64 <= second <= 127:
        return False
    return True


def _lan_ipv4s() -> list[str]:
    if settings.lan_host:
        return [settings.lan_host]
    addresses: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _private_ok(ip) and ip not in addresses:
                addresses.append(ip)
    except OSError:
        pass
    return addresses


def _rpc_allowed(request: Request) -> bool:
    if settings.rpc_secret:
        token = request.headers.get("x-pocket-rpc-token", "")
        return hmac.compare_digest(token, settings.rpc_secret)
    client = request.client.host if request.client else ""
    return client in {"127.0.0.1", "::1", "localhost"}


def _pin_gate_html(kind: str, *, will_redirect: bool = False) -> str:
    label = "公网访问密码" if kind == "public" else "局域网访问密码"
    hint = (
        '<p style="color:#7f838a;margin:14px 0 0;font-size:13px">验证后将在本机浏览器打开 PureGamma 正式站点</p>'
        if will_redirect
        else ""
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>PureGamma AI 访问验证</title></head>'
        '<body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#101216;color:#f5f6f8">'
        '<form method="get" style="text-align:center">'
        '<h2 style="margin-bottom:12px;font-weight:600">PureGamma AI</h2>'
        f'<p style="color:#a2a4a6;margin:0 0 16px">请输入{label}（8 位数字）</p>'
        '<input name="pin" inputmode="numeric" pattern="[0-9]{8}" maxlength="8" autofocus '
        'style="font-size:20px;padding:10px 14px;border-radius:10px;border:1px solid #3a3d44;background:#191c22;color:#f5f6f8;text-align:center;letter-spacing:4px" />'
        '<button type="submit" style="margin-left:10px;font-size:16px;padding:10px 18px;border-radius:10px;border:0;background:#d6b35a;color:#101216;font-weight:600;cursor:pointer">进入</button>'
        f"{hint}"
        '</form></body></html>'
    )


def _forwarded_query(request: Request) -> str:
    """转发查询串，但不把访问 PIN 带进上游。

    PIN 以前是原样转发的，于是它会出现在上游的访问日志、Referer 和 Next.js 的
    跳转 Location 里（`/zh?pin=12345678`），既泄漏又无用。
    """
    return urlencode([(key, value) for key, value in request.query_params.multi_items() if key != PIN_PARAM])


async def _proxy_http(request: Request) -> Response:
    target = urljoin(settings.web_target + "/", request.url.path.lstrip("/"))
    query = _forwarded_query(request)
    if query:
        target += "?" + query
    host = request.headers.get("host", "")
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "connection", "accept-encoding"}
    }
    headers["x-forwarded-host"] = host
    headers["x-forwarded-proto"] = "https" if _kind_for_host(host.split(":")[0]) == "public" else "http"
    body = await request.body()
    client = _upstream_client()
    try:
        upstream_request = client.build_request(request.method, target, headers=headers, content=body or None)
        upstream = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        return JSONResponse({"detail": "upstream unavailable", "error": str(exc)[:200]}, status_code=502)
    resp_headers = {
        key: value for key, value in upstream.headers.items()
        if key.lower() not in {"content-length", "transfer-encoding", "connection", "content-encoding", "keep-alive"}
    }
    return StreamingResponse(_stream_upstream(upstream), status_code=upstream.status_code, headers=resp_headers)


async def _authorized_response(request: Request, *, tunnel: bool) -> Response:
    """已通过 PIN / 配对 cookie 的请求：隧道入口交回正式站点，其余入口代理上游。"""
    if tunnel:
        handoff = await _app_handoff(request)
        if handoff is not None:
            return handoff
    return await _proxy_http(request)


class ProxyMiddleware(BaseHTTPMiddleware):
    """所有未保留路径的 HTTP 请求：先 PIN 鉴权。

    鉴权通过后按入口域名分流：
    - 临时隧道域名（*.trycloudflare.com）：跳转到 POCKET_APP_ORIGIN 的正式站点，
      因为隧道域名与正式站点不同源，代理出来的整站无法调用接口；
    - 其他入口（局域网、已配置的稳定公网域名）：反向代理到 puregamma web。
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(RESERVED_PREFIXES):
            return await call_next(request)
        if request.method not in settings.allowed_methods:
            return JSONResponse({"detail": "method not allowed"}, status_code=405)
        host = request.headers.get("host", "").split(":")[0]
        kind = _kind_for_host(host)
        tunnel = _is_tunnel_host(host)
        paired = _cookie_authorized(request.cookies.get(COOKIE_NAME), kind)
        provided = request.query_params.get(PIN_PARAM, "")

        # 已配对的手机不受限速影响：攻击者的噪声不该把主人锁在门外
        if not paired and _pin_failures_from(_client_ip(request)) >= PIN_FAILURE_LIMIT:
            return _throttled_response()

        if paired:
            return await _authorized_response(request, tunnel=tunnel)

        # PIN 首次通过：发会话 cookie，避免每个请求都要重新带上 ?pin=（旧实现里
        # _authorized 会先匹配 ?pin= 并直接返回，发 cookie 的分支根本到不了）。
        if provided and _pin_matches(provided, kind):
            _clear_pin_failures(_client_ip(request))
            response = await _authorized_response(request, tunnel=tunnel)
            response.set_cookie(COOKIE_NAME, _cookie_value(kind), max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
            return response

        if provided:
            _record_pin_failure(_client_ip(request))

        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            will_redirect = tunnel and bool(settings.app_origin)
            return HTMLResponse(_pin_gate_html(kind, will_redirect=will_redirect), status_code=401)
        return JSONResponse({"detail": "PIN required"}, status_code=401)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    auto_recover(manager)
    try:
        yield
    finally:
        await _close_upstream_client()


app = FastAPI(lifespan=_lifespan, title="PureGamma Pocket Relay")
app.add_middleware(ProxyMiddleware)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "target": settings.web_target, "tunnel": manager.status()}


# ---------- RPC（管理面：默认仅本机，或 rpc_secret） ----------

def _require_rpc(request: Request) -> None:
    if not _rpc_allowed(request):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="RPC not allowed from this host")


@app.get("/rpc/status")
async def rpc_status(request: Request) -> dict:
    _require_rpc(request)
    tunnel = manager.status()
    return {
        "target": settings.web_target,
        "port": settings.port,
        # SaaS：删除局域网（LAN）段——云主机无家庭 LAN，且本地 IP 链接会暴露服务器地址。
        "public": {
            "running": bool(tunnel["running"]),
            "url": tunnel["public_url"],
            "pin": get_public_pin(),
            "custom": pin_is_custom("public"),
            "auto_start": was_auto_start(),
            "last_error": tunnel["last_error"],
        },
        "session": {"restart_requires_relogin": True},
    }


@app.post("/rpc/tunnel/start")
async def rpc_tunnel_start(request: Request) -> dict:
    _require_rpc(request)
    rotate_public_pin()
    save_auto_start(True)
    url = manager.start()
    return {"running": bool(url), "url": url, "pin": get_public_pin(), "last_error": manager.status()["last_error"]}


@app.post("/rpc/tunnel/stop")
async def rpc_tunnel_stop(request: Request) -> dict:
    _require_rpc(request)
    save_auto_start(False)
    manager.stop()
    return {"running": False}


@app.post("/rpc/pin/rotate")
async def rpc_pin_rotate(request: Request) -> dict:
    _require_rpc(request)
    body = await request.json()
    which = str(body.get("which", "public"))
    if which == "public":
        value = rotate_public_pin()
    elif which == "lan":
        value = refresh_lan_pin()
    else:
        return JSONResponse({"detail": "unknown kind"}, status_code=400)
    return {which: value}


@app.post("/rpc/pin/custom")
async def rpc_pin_custom(request: Request) -> dict:
    _require_rpc(request)
    body = await request.json()
    try:
        value = set_custom_pin(str(body.get("which", "")), str(body.get("pin", "")))
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    return {str(body.get("which")): value}


@app.get("/rpc/qr")
async def rpc_qr(request: Request, kind: str = "lan", host: str = "") -> Response:
    _require_rpc(request)
    if kind != "public":
        return JSONResponse({"detail": "LAN access is disabled on this deployment"}, status_code=400)
    url = manager.status().get("public_url") or ""
    if not url:
        return JSONResponse({"detail": "no URL available"}, status_code=400)
    return Response(content=make_qr(url), media_type="image/png")


# ---------- 内置「手机访问」控制页（独立可用；接入 apps/web 后由前端面板替代） ----------

_POCKET_UI = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PureGamma 手机访问</title>
<style>
body{font-family:system-ui;background:#101216;color:#f5f6f8;margin:0;padding:24px;max-width:720px;margin:0 auto}
h1{font-size:20px}h2{font-size:15px;margin:20px 0 8px}.card{background:#191c22;border:1px solid #2a2d34;border-radius:14px;padding:16px;margin-bottom:12px}
.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.muted{color:#a2a4a6;font-size:13px}
.pin{font-size:26px;letter-spacing:6px;font-weight:600;color:#d6b35a}button{background:#d6b35a;color:#101216;border:0;border-radius:8px;padding:8px 14px;font-weight:600;cursor:pointer;font-size:13px}
button.secondary{background:#2a2d34;color:#f5f6f8}img{border-radius:10px;background:#fff;padding:6px}a{color:#7fb3ff}
</style></head><body>
<h1>📱 手机访问</h1>

<div class="card"><h2>🌐 公网（cloudflared 隧道）</h2>
<div class="row"><button id="tunnel-btn" onclick="toggleTunnel()">开启公网访问</button><span class="muted" id="tunnel-state">未开启</span></div>
<div class="row" style="margin-top:10px"><img id="pub-qr" alt="PUB QR"><div>
<div class="pin" id="pub-pin">—</div><div class="muted" id="pub-url"></div>
<div class="row" style="margin-top:8px"><button class="secondary" onclick="rot('public')">刷新密码</button></div></div></div></div>
<div class="card muted">目标：<span id="target"></span> · 服务重启后手机需重新输入密码 · RPC 仅本机/密钥</div>
<script>
const J=(o)=>JSON.stringify(o);
async function load(){const s=await (await fetch('/rpc/status')).json();
document.getElementById('pub-pin').textContent=s.public.pin;
document.getElementById('tunnel-state').textContent=s.public.running?('运行中 '+s.public.url):'未开启';
document.getElementById('tunnel-btn').textContent=s.public.running?'关闭公网访问':'开启公网访问';
if(s.public.running){document.getElementById('pub-url').textContent=s.public.url;
document.getElementById('pub-qr').src='/rpc/qr?kind=public';}
document.getElementById('target').textContent=s.target;}
async function toggleTunnel(){const s=await (await fetch('/rpc/status')).json();
const action=s.public.running?'stop':'start';
await fetch('/rpc/tunnel/'+action,{method:'POST'});load();}
async function rot(which){await fetch('/rpc/pin/rotate',{method:'POST',headers:{'Content-Type':'application/json'},body:J({which})});load();}
load();
</script></body></html>"""


@app.get("/_pocket", response_class=HTMLResponse)
async def pocket_ui() -> str:
    return _POCKET_UI


# ---------- WebSocket 透传 ----------

@app.websocket("/{path:path}")
async def ws_proxy(websocket: WebSocket, path: str):
    host = websocket.headers.get("host", "").split(":")[0]
    kind = _kind_for_host(host)
    if not _ws_authorized(websocket, kind):
        if websocket.query_params.get(PIN_PARAM, ""):
            _record_pin_failure(_client_ip(websocket))
        await websocket.close(code=4403)
        return
    await websocket.accept()
    scheme = "wss" if settings.web_target.startswith("https") else "ws"
    target_host = settings.web_target.split("://", 1)[1]
    target_uri = f"{scheme}://{target_host}/{path}"
    query = str(websocket.query_params)
    if query:
        target_uri += "?" + query
    try:
        async with wsclient.connect(target_uri) as upstream:
            async def client_to_upstream():
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])
            async def upstream_to_client():
                async for message in upstream:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)
            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
