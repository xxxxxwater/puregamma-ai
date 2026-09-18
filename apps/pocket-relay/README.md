# PureGamma Pocket Relay（手机访问）

把 puregamma.AI 的 web 装进口袋：自托管 FastAPI 服务，手机扫码 + 8 位密码即可
局域网 / 公网访问同一个界面，实时同步（HTTP 流式 + WebSocket 透传）。

设计参考 dsh-pocket（cloudflared 快速隧道 + 二维码 + 8 位密码），复刻其机制并
适配 puregamma 技术栈（FastAPI + httpx + qrcode + websockets）。

## 运行

    cd apps/pocket-relay
    pip install -r requirements.txt
    export POCKET_WEB_TARGET=http://localhost:3000
    uvicorn main:app --host 0.0.0.0 --port 8788

## 访问

- 内置控制页：http://<本机>:8788/_pocket（二维码 + 密码 + 隧道开关）
- 局域网：手机连同一网络，扫控制页的局域网二维码，输入 8 位局域网密码
- 公网：控制页点「开启公网访问」→ cloudflared 快速隧道 → 扫公网二维码，
  输入 8 位公网密码（每次开启自动换新，可自定义固定）

公网入口的两种情况（由 `POCKET_APP_ORIGIN` 决定）：

1. 已配置正式站点（SaaS 部署）：隧道是随机 `*.trycloudflare.com` 域名，与
   正式站点不同源——从隧道域名调用 `api.<域名>` 会被 CORS 预检拒绝，会话
   cookie（`Domain=.<域名>; SameSite=Lax`）在 iOS 上算第三方 cookie，登录保持
   不住。所以 PIN 通过后中继把浏览器**跳转到正式站点**（保留路径，去掉 pin
   参数），手机拿到的是完整可用的 PureGamma。
   若同时配置了 `POCKET_HANDOFF_URL`，中继会先用 `POCKET_RPC_SECRET` 向 API
   换一张**一次性、60 秒**的登录交接码，手机在正式站点上直接建立会话——即
   「扫码 + 8 位密码」就够了，不必再走邮箱 / Google 登录。换不到就退回普通
   跳转，手机自行登录。
2. 未配置（自托管 / 局域网）：在入口域名上直接反向代理整站，保持原有行为。

要让公网入口本身就是一个「密码在前、整站在后」的独立域名（无需跳转），把稳定
域名（如 `pocket.example.com`，与正式站点同 registrable domain）指向本服务，
并加入 `POCKET_PUBLIC_HOSTS`：同源 + 同站 cookie 让整站在该域名下直接可用。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| POCKET_WEB_TARGET | http://localhost:3000 | 要代理的 puregamma web 目标 |
| POCKET_PORT | 8788 | 服务监听端口 |
| POCKET_STATE_DIR | ./pocket_state | PIN / 隧道状态 / cloudflared 二进制目录 |
| POCKET_CLOUDFLARED_PATH | 自动下载 | cloudflared 二进制路径 |
| POCKET_RPC_SECRET | 仅本机 | RPC 管理密钥（HTTP 头 x-pocket-rpc-token） |
| POCKET_AUTO_START_PUBLIC | true | 重启后自动恢复公网隧道 |
| POCKET_SESSION_TTL_DAYS | 365 | 登录 cookie 有效期 |
| POCKET_CLOUDFLARED_MIRRORS | 官方源 | cloudflared 下载镜像（逗号分隔） |
| POCKET_APP_ORIGIN | 空 | 公网 PIN 通过后跳转的正式站点（如 https://app.example.com）；空 = 在入口域名上直接代理整站 |
| POCKET_PUBLIC_HOSTS | 空 | 除 *.trycloudflare.com 外按「公网入口」对待的域名（逗号分隔），用于稳定域名 |
| POCKET_HANDOFF_URL | 空 | SaaS API 的一次性登录交接接口（compose 内网，如 http://api:8000/api/mobile-access/session-handoff）；配置后 PIN 通过即免邮箱登录 |

## RPC（管理面，默认仅本机）

- GET  /rpc/status       状态（LAN 地址/密码、隧道 URL/密码、自动恢复）
- POST /rpc/tunnel/start 开启公网隧道（自动轮换公网密码并持久化自动恢复）
- POST /rpc/tunnel/stop  关闭公网隧道
- POST /rpc/pin/rotate   轮换密码 {which: public|lan}
- POST /rpc/pin/custom   自定义密码 {which: public|lan, pin: 12345678}
- GET  /rpc/qr           二维码 PNG（kind=lan|public）

## 安全边界

- 公网 / 局域网密码分开，各为 8 位数字；首次通过 PIN 时发 HMAC 会话 cookie
  （旧实现漏发，每个请求都得重新带 `?pin=`），服务重启后所有手机需重新输入
  （会话绑定进程级密钥）。
- PIN 只守入口：只配置了 `POCKET_APP_ORIGIN` 时它就是一道入口仪式，真正的
  访问控制是正式站点的账号登录；一旦配置 `POCKET_HANDOFF_URL`，8 位密码即
  等同 `POCKET_REMOTE_EMAIL` 那个账号的登录凭证——所以中继对 PIN 失败按客户端
  地址限速（10 次 / 15 分钟，配对成功的手机不受影响），并建议设一个强 PIN。
- 代理只转发白名单 HTTP 方法；跳转不跟随；上游错误如实返回 502，绝不伪造内容。
- 访问 PIN 不会转发给上游（不进上游日志 / Referer / 跳转 Location）。
- 上游响应按流透传：中继全进程共用一个 httpx 客户端，客户端生命周期覆盖整个
  响应体（否则大页面会在中途被截断，cloudflared 只会给手机返回 Cloudflare 520）。
- cloudflared 快速隧道 URL 随机分配，关闭/重启即作废。
- 生产部署建议：POCKET_RPC_SECRET 必设；隧道 URL 与二维码不要外发。
