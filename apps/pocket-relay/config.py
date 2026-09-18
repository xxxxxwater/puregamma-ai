from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PocketSettings:
    # 要代理暴露的 puregamma web 目标（本地实例或已部署站点）
    web_target: str = os.getenv("POCKET_WEB_TARGET", "http://localhost:3000").rstrip("/")
    # pocket 服务自身监听端口
    port: int = int(os.getenv("POCKET_PORT", "8788") or 8788)
    # 状态 / PIN / cloudflared 二进制持久化目录
    state_dir: str = os.getenv("POCKET_STATE_DIR", "./pocket_state")
    # cloudflared 二进制路径；留空则自动下载到 state_dir
    cloudflared_path: str = os.getenv("POCKET_CLOUDFLARED_PATH", "")
    # RPC 管理接口共享密钥（与访问 PIN 独立；留空则仅允许本机访问 RPC）
    rpc_secret: str = os.getenv("POCKET_RPC_SECRET", "")
    # 服务重启后是否自动恢复之前开着的公网隧道
    auto_start_public: bool = os.getenv("POCKET_AUTO_START_PUBLIC", "true").lower() == "true"
    # 登录 cookie 有效期（会话保持）
    session_ttl_days: int = int(os.getenv("POCKET_SESSION_TTL_DAYS", "365") or 365)
    # 局域网访问地址手动覆盖（自托管主机用；空 = 自动探测，过滤 docker 内网段）
    lan_host: str = os.getenv("POCKET_LAN_HOST", "")
    # cloudflared 下载镜像（逗号分隔，逐个尝试；空 = 官方源）
    cloudflared_mirrors: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            u.strip() for u in os.getenv("POCKET_CLOUDFLARED_MIRRORS", "").split(",") if u.strip()
        )
    )
    # 允许公网访问的 HTTP 方法白名单（避免隧道被用于上传等）
    allowed_methods: tuple[str, ...] = ("GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE")
    # 公网 PIN 通过后手机跳转到的正式站点 origin（空 = 在入口域名上直接代理整站）。
    # 临时隧道域名与正式站点不同源，接口调用会被 CORS / 第三方 cookie 挡掉，
    # 所以 SaaS 部署把它设为 https://<APP_DOMAIN>，让手机落到可用的正式站点。
    app_origin: str = os.getenv("POCKET_APP_ORIGIN", "").rstrip("/")
    # SaaS API 的「一次性登录交接」接口（仅 compose 内网可达，如
    # http://api:8000/api/mobile-access/session-handoff）。留空 = 关闭：
    # PIN 通过后只跳到正式站点，手机还需要自己登录一次。
    handoff_url: str = os.getenv("POCKET_HANDOFF_URL", "").strip()
    # 除 *.trycloudflare.com 之外，按「公网入口」对待的域名（逗号分隔）：
    # 用于以后把稳定域名（如 pocket.puregamma.ai）挂在同一个中继上。
    public_hosts: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            host.strip().lower() for host in os.getenv("POCKET_PUBLIC_HOSTS", "").split(",") if host.strip()
        )
    )


settings = PocketSettings()
