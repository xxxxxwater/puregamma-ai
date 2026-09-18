from __future__ import annotations

"""运营商「手机访问」面板后端：把自托管 pocket-relay 的 RPC 代理进 SaaS API。

pocket-relay（apps/pocket-relay）是独立自托管服务：cloudflared 隧道 + 二维码 +
8 位密码，把 puregamma web 暴露到手机（局域网 + 公网），作为 iMessage 中继的
备选访问路径。本路由复用其 RPC，不复制其状态。

SaaS 权限模型：
- 所有登录用户：可查看状态与二维码（status / qr），用于手机扫码访问；
- 仅管理员：隧道开关与密码轮换/自定义（tunnel / pin 变更）。
"""

import hmac
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user, get_db, require_admin
from apps.api.i18n import resolve_locale
from apps.api.routers.mobile_auth import WEB_SESSION_TTL_SECONDS, mint_web_session
from packages.database.models import User, utcnow

router = APIRouter(prefix="/api/mobile-access", tags=["mobile-access"])
logger = logging.getLogger("puregamma.api")


def _admin(user: User = Depends(get_current_user)) -> User:
    require_admin(user)
    return user


def _require_configured() -> tuple[str, str]:
    settings = get_settings()
    if not settings.pocket_relay_url:
        raise HTTPException(status_code=503, detail="POCKET_RELAY_URL is not configured")
    return settings.pocket_relay_url.rstrip("/"), settings.pocket_rpc_secret


async def _forward(request: Request, path: str, *, params: dict[str, str] | None = None) -> Response:
    base, secret = _require_configured()
    target = f"{base}/rpc/{path}"
    if params:
        target += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    headers = {"x-pocket-rpc-token": secret} if secret else {}
    if request.headers.get("content-type"):
        headers["content-type"] = request.headers["content-type"]
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            upstream = await client.request(
                request.method, target, headers=headers, content=await request.body() or None
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"pocket relay unreachable: {str(exc)[:200]}") from exc
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


@router.get("/status")
async def mobile_access_status(request: Request, user: User = Depends(get_current_user)) -> Response:
    response = await _forward(request, "status")
    if response.status_code == 200:
        try:
            payload = json.loads(response.body)
        except (ValueError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            payload["is_admin"] = user.role == "admin"
            # SaaS：取消本地 IP 手机链接（LAN 段在云主机上无意义且会暴露服务器地址），
            # 用户面板只保留公网隧道；LAN 段从响应中剥离。
            payload.pop("lan", None)
            return JSONResponse(payload)
    return response


@router.post("/tunnel/start")
async def mobile_access_tunnel_start(request: Request, _: User = Depends(_admin)) -> Response:
    return await _forward(request, "tunnel/start")


@router.post("/tunnel/stop")
async def mobile_access_tunnel_stop(request: Request, _: User = Depends(_admin)) -> Response:
    return await _forward(request, "tunnel/stop")


@router.post("/pin/rotate")
async def mobile_access_pin_rotate(request: Request, _: User = Depends(_admin)) -> Response:
    return await _forward(request, "pin/rotate")


@router.post("/pin/custom")
async def mobile_access_pin_custom(request: Request, _: User = Depends(_admin)) -> Response:
    return await _forward(request, "pin/custom")


# ---------- 手机远程访问的登录交接（中继专用） ----------

def _phone_locale(request: Request) -> str:
    """把手机浏览器的 Accept-Language 收敛成站点支持的 en/zh。"""
    header = request.headers.get("accept-language", "").lower()
    return "zh" if header.startswith("zh") or "zh-" in header[:24] else "en"


@router.post("/session-handoff")
async def mobile_access_session_handoff(request: Request, db: Session = Depends(get_db)) -> dict:
    """PIN 通过后，为手机签发一次性登录交接（手机不再走邮箱/Google 登录）。

    信任边界：只有持有 POCKET_RPC_SECRET 的中继能调用——该密钥只在 compose
    网络内传递，公网拿不到；对接账号由 POCKET_REMOTE_EMAIL 指定。签发的交接码
    一次性、60 秒过期，只有消费时才会写入会话 cookie。
    """
    settings = get_settings()
    provided = request.headers.get("x-pocket-rpc-token", "")
    if not settings.pocket_rpc_secret or not hmac.compare_digest(provided, settings.pocket_rpc_secret):
        raise HTTPException(status_code=403, detail={"code": "RELAY_TOKEN_REJECTED"})
    email = settings.pocket_remote_email
    if not email or not settings.api_public_url:
        raise HTTPException(status_code=503, detail={"code": "REMOTE_LOGIN_NOT_CONFIGURED"})
    user = db.query(User).filter(func.lower(User.email) == email).one_or_none()
    if not user or not user.email_verified_at:
        raise HTTPException(status_code=503, detail={"code": "REMOTE_LOGIN_ACCOUNT_MISSING"})
    path = mint_web_session(db, user, resolve_locale(header_locale=_phone_locale(request), user=user))
    user.last_login_at = utcnow()
    db.commit()
    logger.info("mobile_access_session_handoff", extra={"user_id": user.id, "email": user.email})
    return {"handoff_url": f"{settings.api_public_url}{path}", "expires_in": WEB_SESSION_TTL_SECONDS}


@router.get("/qr")
async def mobile_access_qr(
    request: Request, kind: str = "lan", host: str = "", user: User = Depends(get_current_user)
) -> Response:
    return await _forward(request, "qr", params={"kind": kind, "host": host})
