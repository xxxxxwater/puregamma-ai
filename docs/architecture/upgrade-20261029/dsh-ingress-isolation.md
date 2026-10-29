# DSH 多租户：入口、Host 隔离、限流审计与上线准备（2026-10-29）

状态：代码与测试，**新能力全部默认关闭**。没有生产部署、数据库迁移、切流或实盘开启。
分支：`upgrade/dsh-ingress-isolation`（基于 `main@0dfad2c`，v0.3.3）。
前置文档：`docs/architecture/upgrade-20261028/dsh-multi-tenant.md`（broker、Host token、overlay，以下简称“v0.3.3 文档”）。

本文按任务顺序记录：§1 入口；§2 Host 隔离与资源上限；§3 速率限制、审计、登出联动；§4 端到端对话对照；§5 上线 runbook 与回滚；§6 开关汇总；§7 测试证据；§8 遗留与需要拍板的事项；§9 交接。

---

## 0. 先修的两个阻断问题（真实浏览器才暴露）

v0.3.3 的证据都在 RPC/HTTP 层（`session-broker.integration.mjs` 用 fetch 调 `session/*`）。这次第一次用真实浏览器通过 broker 打开 DSH Web，发现两个问题：**v0.3.3 的多租户 UI 在浏览器里实际打不开**。

| # | 现象 | 根因 | 修复 |
| --- | --- | --- | --- |
| 0.1 | 页面骨架出现，但 25 个客户端插件一直 pending（sessions、chat、conversation、sidebar…），没有“New Session” | 上游**浏览器端** Session controller 也注入 `fileUpload` 服务，它只由已禁用的 `file-upload` 行的 client face（`@deepseek-ai/dsh-client-file-upload`）提供。v0.3.3 只补了 Host 端的 `fileUploads` | `@puregamma/dsh-file-uploads-refused` 增加 client face：注册浏览器 `fileUpload`，任何上传都返回业务错误 `file-upload/disabled`，没有任何传输（无 fetch、XHR、Worker、Remote）。Host 端把 cordis 设为 external，保证 Service 身份一致（提交 `8aa0e8a`） |
| 0.2 | 经 broker 加载时插件脚本全部 404、MIME 为空 | DSH 用合并 URL `plugins/??a/client.js,b/client.js&rev=…`。broker 的 `targetPath()` 用 `URLSearchParams` 删除 `token` 后重新序列化，把 `??a/…,b/…` 编码成别的路径 | `routeRequest()`/`withoutLaunchToken()` 只在原始查询串上删掉名为 `token` 的参数，其余字节原样转发；单元测试覆盖合并 URL |

以上两项修复后，真实浏览器在根路径与 `/harness` 前缀下都能完整启动 DSH Web（§7）。

## 1. 入口（Caddy / Next → session broker）

### 1.1 调查：DSH Web 能否挂在路径前缀下？——**能**

对 `@deepseek-ai/dsh@0.1.7-rc.1` 真实 Host 的实测与源码核对：

- Host 首页注入 `<base href="./">`。插件 bundle（`plugins/??…`）、`./assets/*`、manifest、favicon 都是相对 URL；launch token 交换的重定向是 `Location: ./`。
- WebSocket：`dsh-api-gateway` 客户端用 `new URL('api/remote.mux', __DSH_TRANSPORT__.streamBaseUrl ?? document.baseURI)`，即相对于页面基址。
- RPC、文件预览等也都基于 `document.baseURI`。
- 实测：一个只转发 `/harness/*`（去掉前缀）的代理后面，真实浏览器加载 DSH Web，全部请求（HTML、插件、静态资源、17 个 RPC POST、1 个 WebSocket 升级）都留在 `/harness/` 之下，**没有任何请求逃逸到根路径**。

### 1.2 选型：生产推荐**独立子域**，前缀作为备选

| | 独立子域 `harness.puregamma.ai`（推荐） | 路径前缀 `app.puregamma.ai/harness/` |
| --- | --- | --- |
| 技术可行性 | 可行（根路径） | 可行（`PUREGAMMA_DSH_BASE_PATH=/harness`，实测通过） |
| 登录态 cookie | 生产 `SESSION_COOKIE_DOMAIN` 必须是 `SITE_URL` 的父域（`config.py` 强制），`pg_session` 为 `Domain=.puregamma.ai; HttpOnly; SameSite=Lax`，子域自然收到；**无需改 cookie** | 同源，自然收到 |
| Origin（`PUREGAMMA_DSH_PUBLIC_ORIGIN`） | `https://harness.puregamma.ai` | `https://app.puregamma.ai` |
| 浏览器安全边界 | DSH 插件脚本运行在**独立 origin**。API 的 CORS 白名单只有 app origin，cookie 认证写操作还要过 API 的 Origin CSRF 校验，所以 DSH 侧的脚本缺陷无法带凭证读写 API | DSH 插件脚本与主站同源：一旦有 XSS，可以带凭证调 API（CORS 信任 app origin），也能读写主站 localStorage。爆炸半径是整个账户 |
| CSP | 可以单独给 DSH 一套宽松 CSP（见 1.4），不影响主站 | DSH 需要 `'unsafe-eval'` 与 `'unsafe-inline'`，同源部署时只能放在路径级 header 上，且同源脚本本身就不受路径隔离 |
| Caddy | 新增一个站点块 | 在 APP 站点内 `handle_path /harness/*`，改动生产站点块 |
| 证书/DNS | 需要新 DNS 记录和证书（Caddy 自动申请） | 不需要 |

结论：生产用独立子域；前缀模式保留给单域 staging 等场景，文档写明它的同源风险。

### 1.3 实现

**broker（`harness/packages/session-broker`）**

- `PUREGAMMA_DSH_BASE_PATH`（默认空，即根路径）。设置后：前缀之外一律 404，而且**不做身份检查、不启动 Host**；裸前缀 308 到带斜杠的形式；Host 返回的根相对 `Location` 改写到前缀下。
- 只在原始查询串上删掉 `token` 参数（见 0.2）。
- 顶层导航放行：`GET/HEAD` + `Sec-Fetch-Mode: navigate` + `Sec-Fetch-Dest: document` + 无 Origin 的请求即使 `Sec-Fetch-Site: cross-site` 也放行（例如从邮件或其他站点点链接进入）。这类请求只读取应用外壳，Lax cookie 也会随之发送。其他跨站请求（fetch、RPC、POST）仍然 403，WebSocket 仍然必须带公开 Origin。
- 每个响应（包括 401/403/404）都加安全头：`Content-Security-Policy`（默认值见 1.4，`PUREGAMMA_DSH_CSP` 可覆盖，设为空串则关闭）、`X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、`Cross-Origin-Opener-Policy: same-origin`。
- `PUREGAMMA_DSH_LOGIN_URL`（可选）：未登录的顶层导航仍返回 401，但正文是一个带登录链接的小页面；其他请求返回 JSON 401。

**Caddy（默认不加载）**

- `deploy/caddy/harness-sessions.caddy`：`{$HARNESS_DOMAIN}` 站点，`request_body max_size 2MB`（Session 面没有上传路由），HSTS/nosniff，`reverse_proxy {$DSH_BROKER_UPSTREAM}`（HTTP 与 WebSocket），`header_up X-Real-IP {client_ip}`（与 API 站点同一规则，不信任 CF-Connecting-IP/X-Forwarded-For），`stream_close_delay 5m`（Caddy 重载配置时不立刻切断 Session WebSocket）。
- `deploy/caddy/Caddyfile.harness-sessions`：`import` 生产 `Caddyfile` 加上述站点。
- `docker-compose.harness-sessions.yml`：compose override。它把生产 `Caddyfile` 挂到 `Caddyfile.base`，再把组合文件挂成 `/etc/caddy/Caddyfile`。`HARNESS_DOMAIN`、`DSH_BROKER_UPSTREAM` 用 `:?` 强制必填。
- **生产 `Caddyfile` 与 `docker-compose.production.yml` 一个字节都没改**。不加 override 时，Caddy 根本没有到 broker 的路由。
- CI（`commercial-release-gate.yml` 的 Caddy 步骤）新增两项：生产 Caddyfile 不得包含 `import`/`HARNESS_DOMAIN`/`DSH_BROKER`；用 `caddy:2-alpine` 按 override 的挂载方式 `caddy validate` 组合配置。

**Next（默认不出现）**

- `NEXT_PUBLIC_DSH_SESSIONS_URL`（构建期，默认空）。设置为 https URL（或 loopback http）时，`/[locale]/chat` 的紧凑页头右侧出现“打开 Harness 会话 / Open Harness sessions”链接：`target=_blank`、`rel="noopener noreferrer"`。
- 带用户名/密码或非 https 的值一律视为未设置。
- Next 只放一个链接，不做反向代理：Next 的 rewrite 不能对 WebSocket 鉴权，同源部署也违背 1.2 的结论。Next 中没有新增任何 Session 状态。

### 1.4 CSP 取舍（实测得出）

默认值：

```text
default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' wss://<公开 host>; worker-src 'self' blob:;
manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

- `'unsafe-inline'`：Host 首页内联了模块加载器和 `__DSH_BOOT__` 清单，内容随插件 rev 变化，无法固定 hash。
- `'unsafe-eval'`：DSH Web 外壳（`dsh-web-frontend` 的 Cordis 客户端 loader）在模块顶层执行 `new Function("ctx","expr","with (ctx) { return eval(expr) }")`，用来求值 `!!js` 配置表达式。没有 `'unsafe-eval'` 时页面直接空白（实测 `EvalError`）。这是上游限制，已列入遗留项。
- 仍然成立的约束：脚本、连接、图片只能来自 broker 自己的 origin（以及 data/blob），不允许任何第三方 origin，`object-src 'none'`，`frame-ancestors 'none'`。
- 这也是选择独立子域的另一个原因：宽松 CSP 只作用在 DSH 自己的 origin 上。

## 6. 开关汇总（全部默认关闭或采用安全值）

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `PUREGAMMA_DSH_BROKER_ENABLED`（v0.3.3） | `false` | broker 不是 `true` 不启动 |
| `PUREGAMMA_DSH_BASE_PATH` | 空（根路径） | 前缀挂载；必须形如 `/harness` |
| `PUREGAMMA_DSH_CSP` | 见 1.4 | 覆盖默认 CSP；空串表示不发送 |
| `PUREGAMMA_DSH_LOGIN_URL` | 空 | 未登录导航的 401 页面里的登录链接；只接受 http(s) |
| `HARNESS_DOMAIN` / `DSH_BROKER_UPSTREAM`（compose override） | 无（必填） | 只有使用 `docker-compose.harness-sessions.yml` 时才需要 |
| `NEXT_PUBLIC_DSH_SESSIONS_URL`（web 构建期） | 空 | 设置后聊天页头出现入口链接 |

## 7. 测试证据（本机实测）

### 7.1 入口

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| broker 入口单元测试 | `tsx --test scripts/session-broker-ingress.test.mjs`（已并入 `session-broker-check`） | 6 passed：路由/前缀/token 剥离（含合并 URL）、前缀外 404 且不调 `/me` 不启动 Host、未登录 401（HTTP/RPC/WS，导航页带登录链接）、跨站 403 与导航放行、本人 Host（HTTP+WS）、Location 改写与安全头 |
| Caddy | `CADDY_BIN=… tsx --test scripts/ingress-caddy.test.mjs`（新 `ingress-check`，没有 caddy 时 2 项 skip） | 3 passed：生产 Caddyfile/compose 未引用；`caddy adapt` 基础配置无 broker 路由、opt-in 配置恰好多一条；**真实 Caddy v2.11.7** 在 broker 前：基础配置下请求不到达 broker，opt-in 下未登录 401（HTTP+WS）、跨站 403（HTTP+WS）、A/B 各到本人 Host、WS 101、HSTS 与 CSP 都在 |
| CI Caddy 步骤 | 本机用 `caddy:2-alpine` 跑新增步骤 | `Valid configuration`，生产 Caddyfile 无引用 |
| 真实 DSH（根路径） | `PG_BROKER_IT_BROWSER=1 PUREGAMMA_DSH_BIN=… tsx scripts/session-broker.integration.mjs` | `# pass 10 / # fail 0`；浏览器：27 个请求 + 1 个 WebSocket（`/api/remote.mux`），0 个越界，0 个控制台错误 |
| 真实 DSH（前缀） | 同上加 `PG_BROKER_IT_BASE_PATH=/harness` | `# pass 10 / # fail 0`；浏览器：27 个请求 + 1 个 WebSocket（`/harness/api/remote.mux`），0 个越界，0 个控制台错误 |
| Next 入口 | `npx playwright test harness-sessions-entry.spec.ts --workers=1`，不设置 flag 与设置 `NEXT_PUBLIC_DSH_SESSIONS_URL=https://harness.puregamma.test/` 各跑一次 | 每次 2 passed + 2 skipped（chromium + mobile-chrome） |
| web | `pnpm --dir apps/web typecheck`、`lint` | 通过（lint 只有已有的 `no-img-element` 警告） |
| harness 全量 | `pnpm --dir harness run check` | 通过 |

变异测试（去掉守卫后测试必须失败）：

| 变异 | 结果 |
| --- | --- |
| 去掉 Origin/Sec-Fetch-Site 围栏（`if (!sameSite(...))`） | ingress + caddy 2 例失败 |
| 去掉前缀外 404 | 2 例失败 |
| 导航判定不检查 Origin | 1 例失败 |
| 生产 Caddyfile 加 `import …harness-sessions.caddy` | caddy 测试 3 例全部失败 |
| 去掉安全头 | 1 例失败 |
| 恢复 `URLSearchParams` 重新序列化（修复 0.2 之前的代码） | 单元测试“routing”失败；修复前真实浏览器步骤实测为插件 404、页面空白 |
| 移除 client face（修复 0.1 之前的代码） | `public-profile-check` 新增例失败；修复前真实浏览器实测 25 个 entry pending |
