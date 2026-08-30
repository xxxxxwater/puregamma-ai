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

## RPC（管理面，默认仅本机）

- GET  /rpc/status       状态（LAN 地址/密码、隧道 URL/密码、自动恢复）
- POST /rpc/tunnel/start 开启公网隧道（自动轮换公网密码并持久化自动恢复）
- POST /rpc/tunnel/stop  关闭公网隧道
- POST /rpc/pin/rotate   轮换密码 {which: public|lan}
- POST /rpc/pin/custom   自定义密码 {which: public|lan, pin: 12345678}
- GET  /rpc/qr           二维码 PNG（kind=lan|public）

## 安全边界

- 公网 / 局域网密码分开，各为 8 位数字，HMAC 会话 cookie 保持登录；
  服务重启后所有手机需重新输入（会话绑定进程级密钥）。
- 代理只转发白名单 HTTP 方法；跳转不跟随；上游错误如实返回 502，绝不伪造内容。
- cloudflared 快速隧道 URL 随机分配，关闭/重启即作废。
- 生产部署建议：POCKET_RPC_SECRET 必设；隧道 URL 与二维码不要外发。
