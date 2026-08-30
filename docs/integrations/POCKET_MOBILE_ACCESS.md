# Pocket Relay（手机访问 / cloudflared 隧道）

## 1. 定位

手机公网访问 PureGamma web 的**备选路径**（与 iMessage 中继并行，互不替代）：
self-hosted 的 FastAPI 服务把 puregamma web 反向代理出来，局域网扫码直连，
公网走 cloudflared 快速隧道 + 8 位数字密码。机制复刻 dsh-pocket
（cloudflared 快速隧道 + 二维码 + 8 位密码 + 会话保持）。

与 iMessage 中继的关系：
- iMessage 中继（apps/imessage-relay，Mac Mini）负责消息收发；
- pocket 中继（apps/pocket-relay）负责手机浏览器访问；
- 二者共享运营面板与鉴权边界（HMAC 会话、8 位密码、管理面仅本机/密钥）。

## 2. 架构

    手机 ──▶ trycloudflare.com ──▶ cloudflared ──▶ pocket-relay:8788 ──▶ POCKET_WEB_TARGET
                                                   │
                                                   └─ PIN 门禁（8 位）+ 会话 cookie + 流式代理 + WS 透传

权限模型（SaaS）：

    apps/web /mobile-access ──▶ /api/mobile-access/* ──▶ pocket-relay /rpc/*（x-pocket-rpc-token）

- 所有登录用户：查看状态与二维码（status / qr），手机扫码 + 密码即可访问；
- 仅管理员：隧道开关（tunnel/start|stop）与密码轮换/自定义（pin/rotate|custom）。

## 3. 部署

在要暴露 web 的机器（本地 / Mac Mini / 服务器）上：

    cd apps/pocket-relay
    pip install -r requirements.txt
    export POCKET_WEB_TARGET=http://localhost:3000   # 本地实例
    export POCKET_RPC_SECRET=<随机密钥>
    uvicorn main:app --host 0.0.0.0 --port 8788

API 服务器（SaaS 侧，运营面板用）：

    POCKET_RELAY_URL=http://<中继主机>:8788
    POCKET_RPC_SECRET=<与中继相同的密钥>

## 4. 使用

- 打开 https://app.puregamma.ai/mobile-access（管理员），或中继本机
  http://127.0.0.1:8788/_pocket。
- 局域网：扫局域网二维码，输入 8 位局域网密码（可关、可刷新、可自定义固定）。
- 公网：点「开启公网访问」→ cloudflared 快速隧道 → 扫公网二维码，
  输入 8 位公网密码（每次开启自动换新，自定义后固定）。
- 手机登录一次后长期免输；中继进程重启后需重输。

## 5. 安全边界

- 公网/局域网密码分开；会话 cookie 绑定中继进程级密钥；密码轮换后旧会话失效。
- 代理只转发白名单 HTTP 方法，跳转不跟随，上游错误如实返回 502，不伪造内容。
- 管理 RPC 默认仅本机；跨机管理必须设 POCKET_RPC_SECRET（HTTP 头 x-pocket-rpc-token）。
- 隧道 URL 随机分配，关闭/重启即作废；二维码与 URL 不要外发。
- 灰度上线时先在 _pocket 控制页验证，再放开到 /mobile-access 面板。

## 6. 测试

    pytest tests/unit/test_pocket_relay.py
