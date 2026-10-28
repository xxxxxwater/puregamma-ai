# DSH 多租户：每用户一个隔离 Host（2026-10-28）

状态：代码与测试完成，**默认全部关闭**。没有生产部署、生产数据库迁移、切流或实盘开启。
分支：`upgrade/dsh-multi-tenant`（基于 `main@d8b435f`）。

本文件回答一件事：在不新建第二套会话状态机的前提下，怎样让 DSH 原生 Session 列表在多用户站点上安全可用。

---

## 1. 背景与结论

`AGENT_WORKSPACE_UPGRADE_20261028.md` §3 记录的阻塞是：

- 固定版本的 DSH Web（`dsh-v0.1.7-rc.1`）是单操作员运行时：只监听 loopback，靠 launch token 认证，只有一个 Session 存储；
- 所有 `*-legacy-api` provider 都用同一个 `PUREGAMMA_LEGACY_API_TOKEN` 调 FastAPI；
- 因此 `ui-sidebar` 必须禁用。它是 `sidebar.workspaces`（原生 Session 列表）的唯一声明者，而 `ui-workspace` 依赖可以列出、创建服务器目录的 Host 目录选择器。

本次的做法是**不改上游，在外面隔离**：

- 每个 PureGamma 用户对应一个独立的 DSH Web Host 进程，有自己的 `DSH_HOME`、`HOME`、cwd 和 token 文件；
- 一个 broker 负责认证，并且只把请求转发到该用户自己的 Host；
- legacy-api provider 改为读取按用户签发、短期有效的 token 文件；
- 目录选择器换成限定在用户工作区内的沙箱实现。

DSH 本身仍然只有一套 Session / Session Controller / projection / transport，Next.js 没有新增任何会话状态。

## 2. 架构

```text
浏览器 ──https──▶ (边缘代理) ──▶ session broker  (PUREGAMMA_DSH_BROKER_ENABLED=true 才启动)
                                   │ 1. Origin / Sec-Fetch-Site 围栏（WebSocket 必须带公开 Origin）
                                   │ 2. 用用户自己的 cookie/Bearer 调 FastAPI GET /me（短缓存）→ user_id
                                   │ 3. user_id → 唯一 Host（按需启动、限总数、闲置回收）
                                   │ 4. 向 FastAPI 申请该用户的 Host token，写入 0600 文件并轮换
                                   ▼
             127.0.0.1:<随机端口>  dsh puregamma --patch multi-tenant.patch.yml --port 0 --no-open
                                   DSH_HOME=HOME=<root>/<sha256(user)[:32]>/home
                                   cwd=PUREGAMMA_DSH_WORKSPACE_ROOT=<...>/workspace
                                   PUREGAMMA_LEGACY_API_TOKEN_FILE=<...>/legacy-api.token
                                   │
                                   └── *-legacy-api provider ──Bearer(用户 Host token)──▶ FastAPI
```

### 2.1 Session broker（`harness/packages/session-broker`）

| 关注点 | 做法 |
| --- | --- |
| 认证 | 只把 `pg_session` cookie 或 `Authorization: Bearer` 转发给 `GET /me`。按凭证哈希缓存（默认 15 s，未认证结果只缓存 2 s）。同名 cookie 出现两次视为歧义，直接拒绝 |
| 路由 | 只按 `/me` 返回的 `user_id` 查找 Host，没有其他寻址方式。目录名是 `sha256(user_id)` 的前 32 位，用户 id 本身不会出现在路径里 |
| DSH 认证 | 解析 Host 的就绪行 `dsh web: http://127.0.0.1:<port>/?token=<t>`，broker 在服务端用 `GET /?token=` 换取 `dsh-auth-*` cookie。这个 cookie 只保存在 broker 中，每次转发时注入 |
| Host/Origin | 转发时把 Host 改写为 `127.0.0.1:<port>`，Origin 改写为 Host 自身的 origin，以通过 DSH 的 loopback 围栏。浏览器侧的围栏由 broker 自己执行：`Origin` 必须等于 `PUREGAMMA_DSH_PUBLIC_ORIGIN`，`Sec-Fetch-Site: cross-site` 一律拒绝，WebSocket 升级必须带 Origin |
| 剥离 | 发往 Host 的请求去掉用户的 Cookie、Authorization、`X-Forwarded-*`、浏览器带来的 `?token=`；Host 返回的 `Set-Cookie` 不回传给浏览器 |
| WebSocket | `/api/remote.mux` 认证通过后做 TCP 隧道。任一端 `end`/`close`/`error` 都会拆掉整个隧道（`http.Server` socket 是半开模式，只收到 FIN 不会触发 close） |
| 环境变量 | Host 只拿到白名单变量（PATH/LANG/TZ 加上配置的透传项）。`PUREGAMMA_LEGACY_API_TOKEN`、broker 密钥、JWT/SESSION 密钥即使写进透传配置也会被剔除 |
| 容量 | `PUREGAMMA_DSH_MAX_HOSTS` 限制同时运行的 Host 数。满了之后淘汰最久未用、且没有打开 socket 的 Host；如果都在使用，返回 503 `capacity` |
| 回收 | 闲置超过 `PUREGAMMA_DSH_IDLE_MS` 且没有打开的 socket 时停止 Host（先 SIGTERM，5 s 后 SIGKILL），同时删除 token 文件 |
| 失败策略 | 拿不到身份返回 401；FastAPI 不可用返回 503；token 属于其他用户时丢弃 token，返回 503，并且不启动 Host；任何情况下都不会回退到其他 Host |

### 2.2 按用户的 legacy-api 身份

- **FastAPI `POST /internal/dsh/host-tokens`**（`apps/api/routers/internal.py`）：
  - `DSH_MULTI_TENANT_ENABLED=false`（默认）时返回 404。
  - 需要两个凭证：broker 服务密钥 `X-PureGamma-Broker-Secret`（≥32 字符），以及**被服务用户自己的**凭证（session cookie、Bearer，或尚未过期的 Host token）。
  - token 的所有者从用户凭证推出，不读请求体。请求体里的 `expected_user_id` 与凭证不一致时返回 409，防止 broker 的缺陷把 A 的 token 写进 B 的 Host。
- **Host token**（`apps/api/dependencies.py`）：
  - HS256 JWT，包含 `aud=puregamma-dsh-host`、`scope=dsh-host`、`sv`、`auth_time`、`jti`；不含 email 和 role。
  - 有效期 ≤ 900 s（默认 600 s）。
  - 只能作为 Bearer 使用；放进 session cookie 会被拒绝。
  - 用户登出（`session_version` 递增）后立即失效。
  - 轮换时沿用最初的 `auth_time`。超过 `DSH_HOST_SESSION_MAX_SECONDS`（默认 8 h）后必须重新登录。
- **路由白名单**：
  - 可访问：`/me`(GET)、`/market`、`/news`(GET)、`/options`、`/research`、`/backtest(-lab)`、`/portfolio`、`/billing`、`/notifications`、`/memory`、`/secretary`、`/gateway`(GET)。
  - 一律 403：`/internal/*`（不能再签发 token）、`/admin/*`、`/auth/*`、`DELETE /me`、`/me/export`、Gateway key 写操作（不能借短期 token 换取长期凭证）。
  - 代价：多租户模式下，auth provider 的登出、引导、语言设置，admin/data-sources 工具，以及 Gateway key 管理都会返回 403。这些操作仍在 Web 应用中完成。
- **`@puregamma/dsh-legacy-auth`**：所有 legacy-api provider 新增 `authTokenFile` 和 `authTokenCacheMs`（默认 5 s）选项。
  - 每次请求都读文件，经过短缓存，因此 broker 轮换 token 时不需要重启 Host。
  - 配置了文件后**不会回退**到共享 env token。文件缺失、可被组或其他用户读取、为空或格式异常时都视为没有 token，provider 的这次调用失败。
  - profile 中的 14 个 provider 行都写了 `authTokenFile: !!js process.env.PUREGAMMA_LEGACY_API_TOKEN_FILE`。单操作员模式下这个变量未设置，行为与之前相同。

### 2.3 Profile

| 行 | 基础 profile（单操作员） | 叠加 `multi-tenant.patch.yml`（仅 broker 传入） |
| --- | --- | --- |
| `ui-sidebar` | 禁用 | **启用** |
| `ui-workspace` | 上游默认 | **显式启用** |
| `directory-picker`（上游 auto，可浏览整个 Host 文件系统并创建目录） | **禁用** | 禁用 |
| `puregamma-directory-picker` → `@puregamma/dsh-directory-picker-sandbox` | 挂载，root 未设置时一律失败 | 挂载，root = 用户工作区 |
| `puregamma-ui-directory-picker` → 上游 browse 客户端 UI | 挂载 | 挂载 |
| `file-upload`（上游通用上传） | 禁用 | 禁用 |
| `puregamma-file-uploads-refused` | 挂载（见 §5.2） | 挂载 |
| shell / fs 工具、terminal、workspace-files、plugin manager、ptc/minimal/cordis preset | 禁用 | 禁用（叠加层只能改上面两行，测试强制） |

**沙箱目录选择器**提供与上游相同的 `browse` capability，所以 `directoryPicker` Remote、ui-workspace 和 browse UI 都不用改。具体行为：

- 请求路径和每个条目都先 `realpath`，结果必须在 `realpath(root)` 之内。`..`、绝对路径逃逸、指向外部的符号链接、与 root 同前缀的兄弟目录都会被拒绝或从结果中省略；
- `createDirectory` 一律拒绝；
- 隐藏目录默认不显示，单次列出最多 500 项；
- `pick()` 返回 root，供进程内调用方使用。上游控制器只把 `pick` 路由给 `native` 后端，所以经过网络调用时它返回 `directory-picker/unavailable`，与上游行为一致。

## 3. 威胁模型

| 威胁 | 控制 | 证据 |
| --- | --- | --- |
| 用户 A 读取或修改 B 的 Session | 每用户独立进程和 `DSH_HOME`，路由只按 `/me` 的 user_id | 集成测试（真实 DSH）；单元测试 `each user reaches only their own Host` |
| 未认证访问 | 认证在 Host 查找之前完成，不启动 Host | 401（HTTP、RPC、WebSocket，真实 DSH） |
| CSRF / 跨站 WebSocket 劫持 | broker 校验 Origin 和 Sec-Fetch-Site，WebSocket 必须带公开 Origin | 403 测试（真实 DSH 与单元测试） |
| launch token 或 DSH cookie 泄露给浏览器 | token 交换在服务端完成，浏览器带来的 `?token=` 被剥离，`Set-Cookie` 不回传 | 单元测试 |
| 用户的 PureGamma 会话 cookie 泄露给 Host 或模型 | 发往 Host 的请求剥离 Cookie 和 Authorization | 单元测试 |
| 共享 legacy token 被所有用户共用 | 每用户 token 文件；Host 环境变量白名单剔除共享 token | `legacy-auth-check`、单元测试 |
| Host token 被窃取后扩权 | ≤15 min、只作 Bearer、路由白名单、不能签发 token 或创建 Gateway key、登出即失效、`auth_time` 上限 | `tests/security/test_dsh_host_tokens.py`（10 例） |
| broker 缺陷导致 token 写错用户 | 服务端校验 `expected_user_id`（409），broker 校验返回的 `user_id` | pytest 与单元测试（`user-evil`） |
| 浏览服务器目录 | 沙箱选择器加 realpath 包含校验，不能创建目录 | `directory-picker-check`（含变异测试），真实 DSH 中 `/`、`/etc`、B 的 root、`..` 都被拒绝 |
| 资源耗尽 | Host 数上限、单 Host 堆上限（`PUREGAMMA_DSH_HOST_HEAP_MB`）、闲置回收 | 单元测试 |
| Codex/ChatGPT 登录凭证被托管使用（§9） | 没有任何 profile 行挂载 Codex 或 ChatGPT 登录 provider；仓库代码不读取 `~/.codex`、`CODEX_HOME` 或 `codex login` | `codex-guard-check` |

**剩余风险（需在部署侧处理）**：

- 所有 Host 以同一个 OS 用户运行，隔离只在进程和目录层面，不是内核层面。公开实例应当让每个 Host 使用独立的 uid、容器或 VM，或至少配合 seccomp/AppArmor。
- 公开 profile 已经禁用 shell 和 fs 工具，所以模型无法直接访问磁盘。但上游 `session/create` 接受任意 `cwd`。它目前只影响会话元数据，因为 fs 和 workspace-files 都已禁用；将来如果开放任何文件能力，必须先在 Session 层限定 cwd。
- broker 自己不做速率限制，应当由边缘代理负责。

## 4. 开关与配置（全部默认关闭或采用安全值）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `PUREGAMMA_DSH_BROKER_ENABLED` | `false` | 不是 `true` 时 broker 拒绝启动（退出码 2） |
| `PUREGAMMA_DSH_BROKER_SECRET` / `DSH_BROKER_SECRET` | 空 | 双方共享的服务密钥，≥32 字符 |
| `DSH_MULTI_TENANT_ENABLED`（API） | `false` | 关闭时 token 签发端点返回 404；生产配置校验要求开启时必须有足够强的密钥 |
| `DSH_HOST_TOKEN_TTL_SECONDS` / `DSH_HOST_SESSION_MAX_SECONDS` | 600 / 28800 | Host token 有效期 / 轮换链的最长时间 |
| `PUREGAMMA_DSH_PUBLIC_ORIGIN` | `http://127.0.0.1:3480` | 唯一接受的 Origin |
| `PUREGAMMA_DSH_BROKER_HOST` / `_PORT` | `127.0.0.1` / 3480 | 监听地址 |
| `PUREGAMMA_DSH_BIN` | 空（必填） | 固定版本的 DSH 启动器 `@deepseek-ai/dsh/lib/bin.js` |
| `PUREGAMMA_DSH_HOSTS_ROOT` | `./.dsh-hosts` | 每用户状态根目录（0700） |
| `PUREGAMMA_DSH_MAX_HOSTS` / `_IDLE_MS` / `_HOST_HEAP_MB` | 8 / 15 min / 1024 | 容量、闲置回收、单 Host 堆上限 |
| `PUREGAMMA_DSH_HOST_ENV_PASSTHROUGH` | 空 | 透传给 Host 的变量（例如模型 API key），密钥类变量始终被剔除 |
| `PUREGAMMA_DSH_HOST_API_URL` | 同 `PUREGAMMA_LEGACY_API_URL` | Host 访问 FastAPI 的地址 |

## 5. 实测中发现并已修复的问题

### 5.1 profile 行不能给插件改名

起初 profile 用 `- id: directory-picker` 加新的 `name` 来替换上游选择器。真实 DSH 的 `--dump-config` 显示：

```text
patch: name mismatch for "directory-picker" (expected "@deepseek-ai/dsh-host-directory-picker-auto", got "@puregamma/dsh-directory-picker-sandbox"), skipping
```

结果上游选择器仍在运行：真实 Host 从 `$HOME` 开始列目录，面包屑一直显示到 `/`。

修复：

- 禁用上游行，另插入 `puregamma-directory-picker`；
- `public-profile-surface` 的 `compose()` 按启动器的规则跳过改名行，并新增测试“profile 行不能改名”。旧写法在该测试下 3 例失败。

### 5.2 原生 Session Controller 在 PureGamma profile 中从未激活（`main` 上已存在）

上游 `sessionController` 依赖 `fileUploads`，而 `fileUploads` 只由 `file-upload` 行提供。公开 profile 出于安全考虑禁用了 `file-upload`，所以真实 Host 上所有 `session/*` 调用都返回：

```text
gateway/service-unavailable: active Service "sessionController" is unavailable
```

修复：新增 `@puregamma/dsh-file-uploads-refused`。它注册 `ctx.fileUploads`，但不提供任何能力：

- 不挂载 HTTP 路由，也不暴露 Remote；
- `resolve` 永远找不到 receipt，DSH 因此按 `session/attachment-invalid` 拒绝带附件的 prompt；
- `bindPrompt` 遇到 receipt 时直接抛出异常。

这样 Session Controller 可以挂载，同时通用上传仍保持禁用。

## 6. 版本对齐（Part 1）

- npm 上存在与 gitlink 相同的 `@deepseek-ai/*@0.1.7-rc.1`。Harness 根目录的 devDependencies 和全部插件的 peerDependencies 都已对齐到这个版本，并把 `cordis` 升到 4.0.4、`schemastery` 升到 3.18.4（0.1.7 要求）。没有对上游打补丁。
- 0.1.7 中 `tool.call.toolview` 的 owner props 按 phase 区分（`{ phase: 'preparing'|'start'|'result', block }`）。五个领域 tool view 现在只在 `phase === 'result'` 时显示数值。新增测试：较早 phase 即使带着 result 形状的 block 也不显示数值；回退修复后该测试失败。
- `harness/README.md` 中关于版本的说明已改为“已对齐”。

## 7. 运行方法

```bash
# 构建与检查（含 broker、picker、legacy-auth、codex-guard、profile-surface）
pnpm --dir harness install --no-frozen-lockfile
pnpm --dir harness run check

# 后端
PYTHONPATH=. python -m pytest -q tests/security/test_dsh_host_tokens.py tests/test_auth.py

# 真实 DSH 隔离集成（不在 check 中；会启动两个真实 Host，可用内存不足 2 GB 时拒绝运行）
mkdir -p /tmp/dsh-rt && cd /tmp/dsh-rt && echo '{"private":true,"dependencies":{"@deepseek-ai/dsh":"0.1.7-rc.1"}}' > package.json && pnpm install --ignore-scripts
cd <repo>/harness && PUREGAMMA_DSH_BIN=/tmp/dsh-rt/node_modules/@deepseek-ai/dsh/lib/bin.js npx tsx scripts/session-broker.integration.mjs

# 运行 broker（需同时打开 API 侧 DSH_MULTI_TENANT_ENABLED=true 并配置相同密钥）
PUREGAMMA_DSH_BROKER_ENABLED=true PUREGAMMA_DSH_BROKER_SECRET=... PUREGAMMA_DSH_BIN=... \
PUREGAMMA_DSH_PUBLIC_ORIGIN=https://<站点> node harness/packages/session-broker/lib/main.js
```

## 8. 测试证据（本机实测）

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| Harness 全量 | `pnpm --dir harness run check` | 通过（含新增 `legacy-auth-check` 4 例、`session-broker-check` 9 例、`directory-picker-check` 5 例、`codex-guard-check` 2 例，`public-profile-check` 扩展到 11 例，`domain-toolviews-check` 9 例） |
| Host token | `pytest tests/security/test_dsh_host_tokens.py tests/test_auth.py` | 18 passed |
| 真实 DSH 隔离 | `session-broker.integration.mjs`（`@deepseek-ai/dsh@0.1.7-rc.1`，两个真实 Host） | 见下表 |
| 变异测试 | 去掉 picker 的符号链接或目标包含校验、恢复 toolview 的旧判定、恢复改名行 | 对应测试均失败 |

真实 DSH 集成结果（`<结果待填>`）：

<!-- INTEGRATION-RESULTS -->

## 9. 回滚

- 每个阶段都是独立提交，可以用 `git revert` 单独回退：版本对齐 → token 与 provider 文件 → broker → picker、overlay 与 Codex 守卫 → picker 行修复 → Host 堆配置 → fileUploads 拒绝 provider。
- 运行时回滚：不设置 `PUREGAMMA_DSH_BROKER_ENABLED` 或 `DSH_MULTI_TENANT_ENABLED` 即可。基础 profile 仍保持 `ui-sidebar` 禁用，单操作员 Host 行为与之前相同，只多了沙箱选择器和拒绝型 `fileUploads`。
- 没有数据库迁移。Host token 是无状态 JWT，关闭开关后签发端点返回 404，已签发的 token 最多 15 分钟后过期，并且只能访问白名单路由。

## 10. 仍未完成

- **OS 级隔离**：所有 Host 共用一个 uid（§3）。生产需要每个 Host 独立的 uid、容器或 VM，属于部署工作。
- **从 vendor 源码构建 DSH Web**：本机 `/data` 只剩不到 1 GB 可用空间，共享的 8 GB 内存在本次工作中两次因 OOM 导致整机重启，所以没有执行 `vendor/deepseek-harness` 的完整 install 和 build。集成测试改用与 gitlink 同一 tag 的 npm 发布版 `@deepseek-ai/dsh@0.1.7-rc.1`。
- **带模型的端到端对话**：本机没有模型 API key，所以没有验证 prompt → 工具 → legacy-api 用 Host token 调 FastAPI 的完整链路。token 范围与跨用户隔离由 pytest 覆盖，provider 读文件由 `legacy-auth-check` 覆盖。
- **登出联动**：用户登出后，FastAPI 会立即拒绝 Host token，但 broker 的 `/me` 缓存最长保留 15 s；Host 进程要等闲置回收后才停止。可以考虑由 FastAPI 主动通知 broker。
- **前端入口**：Next.js 还没有指向 broker 的入口或反向代理配置（Caddyfile 不在本工作范围内）。
