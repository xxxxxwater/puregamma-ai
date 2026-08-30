from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import socket
from contextlib import asynccontextmanager
from urllib.parse import urljoin

import httpx
import websockets.asyncio.client as wsclient
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from pin import (
    get_lan_pin,
    get_public_pin,
    pin_for_host,
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
COOKIE_MAX_AGE = settings.session_ttl_days * 86400
RESERVED_PREFIXES = ("/health", "/rpc", "/_pocket")

manager = TunnelManager()


def _kind_for_host(host: str | None) -> str:
    if host and host.endswith("trycloudflare.com"):
        return "public"
    return "lan"


def _pin_for_kind(kind: str) -> str:
    return get_public_pin() if kind == "public" else get_lan_pin()


def _cookie_value(kind: str) -> str:
    return hmac.new(SESSION_KEY.encode(), f"{kind}:{_pin_for_kind(kind)}".encode(), hashlib.sha256).hexdigest()


def _authorized(request: Request, kind: str) -> bool:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and hmac.compare_digest(cookie, _cookie_value(kind)):
        return True
    provided = request.query_params.get("pin", "")
    return bool(provided and hmac.compare_digest(provided, _pin_for_kind(kind)))


def _ws_authorized(websocket: WebSocket, kind: str) -> bool:
    cookie = websocket.cookies.get(COOKIE_NAME)
    if cookie and hmac.compare_digest(cookie, _cookie_value(kind)):
        return True
    provided = websocket.query_params.get("pin", "")
    return bool(provided and hmac.compare_digest(provided, _pin_for_kind(kind)))


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


def _pin_gate_html(kind: str) -> str:
    label = "公网访问密码" if kind == "public" else "局域网访问密码"
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
        '</form></body></html>'
    )


async def _proxy_http(request: Request) -> Response:
    target = urljoin(settings.web_target + "/", request.url.path.lstrip("/"))
    if request.url.query:
        target += "?" + request.url.query
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "connection", "accept-encoding"}
    }
    headers["x-forwarded-host"] = request.headers.get("host", "")
    headers["x-forwarded-proto"] = "https" if request.headers.get("host", "").endswith("trycloudflare.com") else "http"
    body = await request.body()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=120, write=30, pool=10),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            upstream_request = client.build_request(request.method, target, headers=headers, content=body or None)
            upstream = await client.send(upstream_request, stream=True)
            resp_headers = {
                key: value for key, value in upstream.headers.items()
                if key.lower() not in {"content-length", "transfer-encoding", "connection", "content-encoding", "keep-alive"}
            }
            return StreamingResponse(upstream.aiter_bytes(), status_code=upstream.status_code, headers=resp_headers)
    except httpx.HTTPError as exc:
        return JSONResponse({"detail": "upstream unavailable", "error": str(exc)[:200]}, status_code=502)


class ProxyMiddleware(BaseHTTPMiddleware):
    """所有未保留路径的 HTTP 请求：先 PIN 鉴权，再反向代理到 puregamma web。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(RESERVED_PREFIXES):
            return await call_next(request)
        if request.method not in settings.allowed_methods:
            return JSONResponse({"detail": "method not allowed"}, status_code=405)
        kind = _kind_for_host(request.headers.get("host", "").split(":")[0])
        if _authorized(request, kind):
            return await _proxy_http(request)
        provided = request.query_params.get("pin", "")
        if provided and hmac.compare_digest(provided, _pin_for_kind(kind)):
            response = await _proxy_http(request)
            response.set_cookie(COOKIE_NAME, _cookie_value(kind), max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
            return response
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return HTMLResponse(_pin_gate_html(kind), status_code=401)
        return JSONResponse({"detail": "PIN required"}, status_code=401)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    auto_recover(manager)
    yield


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
