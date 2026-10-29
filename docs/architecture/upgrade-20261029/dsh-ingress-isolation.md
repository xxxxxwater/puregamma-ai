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

## 2. Host 进程隔离与资源上限

### 2.1 可插拔 launcher（`PUREGAMMA_DSH_HOST_LAUNCHER`，默认 `direct`）

`harness/packages/session-broker/src/launchers.ts`。broker 只依赖一个接口：生成 launch plan（命令、参数、环境）、把就绪行里的端口映射为连接目标（`{ port, authority }`）、带外停止、启动时清理遗留的 Host。

| launcher | 实现 | 本机真实验证 |
| --- | --- | --- |
| `direct`（默认，兼容 v0.3.3） | broker 的子进程，同一 uid，只有 V8 堆上限 | 真实 DSH 10/10 |
| `systemd` | `systemd-run --user` transient unit：**不需要 root**，每个 Host 一个 `pg-dsh-<instance>-<key16>-<rand>.service`，放在 `pgdsh.slice` | fake Host 内部自检 + 真实 DSH 12/12 |
| `docker` | 每个 Host 一个容器（`docker run --rm --init`），容器内 `container-entry.mjs` 做 loopback 转发 | fake Host 内部自检 + 真实 DSH 12/12 |

**systemd unit 属性**（每一项都在 systemd 257 的 user manager 上实测生效）：

```text
MemoryMax=<memoryMb>M  MemorySwapMax=0  CPUQuota=<cpu>%  TasksMax=<n>  LimitNOFILE=<n>  LimitFSIZE=<bytes>  LimitCORE=0
NoNewPrivileges  PrivateUsers  PrivatePIDs  PrivateTmp  ProtectSystem=strict  ProtectHome=tmpfs  ProtectKernelTunables/Modules
ProtectControlGroups  RestrictNamespaces  RestrictSUIDSGID  RestrictRealtime  LockPersonality  UMask=0077
SystemCallArchitectures=native  SystemCallFilter=@system-service ~@privileged @resources @mount @debug @cpu-emulation @obsolete
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
TemporaryFileSystem=<hostsRoot>:ro 以及 /data /srv /mnt /media /opt（存在才加）
BindReadOnlyPaths=<DSH 安装目录> <harness 目录> <node 所在目录>   BindPaths/ReadWritePaths=<本用户目录>
```

- 环境变量只用 `--setenv=NAME` 传名字，值来自 systemd-run 自己的环境，不出现在命令行上。
- `MemoryDenyWriteExecute` 不能开：V8 JIT 需要 W+X。
- **`IPAddressDeny`/`IPAddressAllow` 在 user manager 中被静默忽略**（实测外网仍然可达），所以不设置，避免造成“已限制网络”的错觉。网络控制见 2.4。

**docker 参数**：

```text
--read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m（docker 默认还有 noexec）
--cap-drop ALL --security-opt no-new-privileges --user <broker uid:gid>
--memory/--memory-swap <m> --cpus <c> --pids-limit <n> --ulimit nofile=<n>:<n> --ulimit fsize=<bytes> --ulimit core=0
--network <PUREGAMMA_DSH_DOCKER_NETWORK> -p 127.0.0.1::3000（只发布到宿主 loopback）
-v <DSH 安装>:ro -v <harness>:ro -v <node 目录>:ro -v <本用户目录>:rw；环境变量只用 -e NAME
```

- 容器以 broker 自己的 uid 运行，所以能读 0600 的 token 文件；隔离来自命名空间和只挂载本用户目录，而不是 uid。
- DSH Web 拒绝绑定非 loopback 地址（`--host 0.0.0.0 is intentionally not supported yet for safety`），而容器的 loopback 从宿主不可达。所以 `container-entry.mjs` 让 DSH 监听容器内 127.0.0.1，再把容器网卡上的 3000 端口转发过去，并且等转发监听好以后才回显就绪行。broker 连接宿主上发布的端口，`Host`/`Origin` 用容器内 DSH 自己的 authority，DSH 的 Host/Origin 围栏和 cookie 认证照常生效。
- 代价：同一 docker 网络上的其他容器可以连到这个转发端口（仍然需要该 Host 的 `dsh-auth` cookie）。部署时应为 Host 建专用网络并关闭 ICC（`com.docker.network.bridge.enable_icc=false`）。

**启动清理**：每个 broker 实例（`PUREGAMMA_DSH_INSTANCE`）在启动时停止同名前缀的 unit，或 `docker rm -f` 带同一 label 的容器。broker 崩溃留下的 Host 因此会在下次启动时被清掉，不会误伤其他实例（测试用随机 instance）。

### 2.2 资源上限覆盖

| 资源 | direct | systemd | docker | 强度 |
| --- | --- | --- | --- | --- |
| 内存 | 仅 V8 堆（`--max-old-space-size`） | cgroup `memory.max` + 禁 swap | `--memory` = `--memory-swap` | 内核强制；超限 OOM 只杀该 Host |
| CPU | 无 | `cpu.max`（CPUQuota） | `--cpus` | 内核强制 |
| 进程/线程数 | 无 | `pids.max`（TasksMax） | `--pids-limit` | 内核强制 |
| 文件描述符 | 继承 | RLIMIT_NOFILE | `--ulimit nofile` | 内核强制 |
| 单文件大小 | 无 | RLIMIT_FSIZE | `--ulimit fsize` | 内核强制（写超限返回 `EFBIG`） |
| 用户目录总量 | broker 检查 | broker 检查 | broker 检查 | **软限制**，见下 |
| `/tmp` | 共享 | 私有（tmpfs 计入 cgroup 内存） | 64 MB tmpfs，noexec | — |

**磁盘配额**（所有 launcher）：`PUREGAMMA_DSH_HOST_DISK_MB`（默认 1024）。

- 启动 Host 前统计用户目录占用（`st_blocks`，不跟随符号链接，最多遍历 20 万项，超过配额即停止计数）。超限时返回 **507 `storage-quota-exceeded`**，不启动 Host，其他用户不受影响。
- 运行中每 `PUREGAMMA_DSH_HOST_DISK_CHECK_MS`（默认 60 s）复查一次，超限就停止该 Host。
- 强度：两次检查之间最多可以多写“写入速率 × 间隔”，单文件受 RLIMIT_FSIZE 硬限制。需要硬性总量时，部署侧可以选：XFS project quota（每用户目录一个 project id）、每用户一个 loop 设备/文件系统、或 docker overlay2 + xfs `pquota` 时的 `--storage-opt size=`。这些都需要 root 和系统级配置，本次没有改动系统全局配置。

### 2.3 实测发现并已修复的问题

| 问题 | 影响 | 修复 |
| --- | --- | --- |
| DSH 启动时总会重写 profile 根目录的 `cordis.yml`，Loader 运行时也可能写回组合树。v0.3.3 把每个用户的 `profiles/puregamma` 直接软链接到共享的 `harness/profile` | direct 模式下所有租户写同一个仓库文件（本机 `harness/profile/cordis.yml` 的 mtime 确实被 Host 改过）；沙箱模式下 profile 只读，DSH 直接 `EROFS` 退出 | 每个用户一个真实的 profile 目录：共享 profile 的每一项都软链接进来，只有 `cordis.yml` 是 0600 的私有副本（`prepareProfile`）。旧的软链接布局会自动迁移 |
| DSH 的原生扩展加载器（`node-addon-native-custom-loader`）把 `.node` 复制到 `os.tmpdir()` 下的缓存再加载 | direct 模式下同 uid 的所有 Host 共享一个可写的可执行缓存（加载前有哈希校验，但存在 TOCTOU）；docker 的 noexec `/tmp` 下 DSH 无法启动 | 所有 Host 设置 `NARB_DISABLE_NATIVE_CACHE=1`，直接从只读安装目录加载 |

### 2.4 方案取舍与生产推荐

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| `direct` | 简单 | 只有进程和目录隔离：同 uid 可以互相 ptrace/信号，能看到彼此的 `/proc`，没有资源上限 |
| `systemd`（user manager） | **broker 不需要任何特权**；独立的 user、PID、mount 命名空间；cgroup 上限；seccomp；其他用户目录和 `/data` 被隐藏；本机全套实测 | Host 与 broker 共用网络命名空间：Host 可以连其他 loopback 服务（包括其他 Host 的端口，但需要对方的 cookie）；user manager 不支持 IP ACL |
| `systemd`（system manager，`User=`/`DynamicUser=`） | 每用户独立 uid，可用 `IPAddressDeny` | broker 能创建 system unit 就等于 root；不同 uid 的 Host 读不了 broker 写的 0600 token 文件（provider 只检查权限位，因此需要 root 帮忙 chown） |
| `docker` | 独立网络命名空间（可配专用网络和出口防火墙）；只读根文件系统；按镜像交付 | broker 需要 docker socket（等于 root）；DSH 不允许非 loopback 绑定，需要容器内转发；镜像需要构建和发布 |
| gVisor / Firecracker 微虚拟机 | 最强 | 运维成本最高，本次未评估实现 |

**推荐生产用 `systemd`**：

- broker 以专用的无特权账号（例如 `pg-dsh`，开启 `loginctl enable-linger`）作为 systemd 服务在宿主机运行。Caddy 容器通过 `DSH_BROKER_UPSTREAM=host.docker.internal:<port>`（或宿主机桥接 IP）访问 broker。
- 网络缺口在部署侧补上：在 `pgdsh.slice` 上加 nftables 规则（`socket cgroupv2 level … "…/pgdsh.slice"`），只放行 FastAPI 和模型 provider 的出口，拒绝其他 loopback 端口和内网。
- 在 slice 上设置总的 `MemoryMax`，限制所有 Host 合计的内存。
- 等迁移到独立 Host 节点，或者需要 Host 级网络命名空间时，切换到 `docker` launcher（专用网络、关闭 ICC、出口防火墙、镜像中预装 node 与 DSH）。

### 2.5 空闲回收在新 launcher 下同样有效

- `systemd`：`reap()` 先 `systemctl --user stop <unit>`，再向 `systemd-run` 子进程发信号。fake Host 测试和真实 DSH 中 unit 都会消失。
- `docker`：`reap()` 执行 `docker stop -t 5`（`--rm` 随后删除容器）。fake Host 测试和真实 DSH 中容器都会消失。
- broker 崩溃后重启：同一 instance 的遗留 unit 被清除（systemd live 测试中模拟了崩溃）。

## 3. 速率限制、并发上限、审计日志、登出联动

### 3.1 准入顺序与限额（`src/limits.ts`、`src/server.ts`）

每个请求按以下顺序检查，任何一步拒绝都会写一条审计记录：

1. 前缀路由
2. Origin / Sec-Fetch-Site 围栏（403）
3. 身份
4. 每用户速率
5. 每用户并发
6. Host（全局启动速率、容量、磁盘配额）

| 限额 | 键 | 默认 | 超限 |
| --- | --- | --- | --- |
| 请求速率（令牌桶） | user_id | 20/s，突发 80 | 429 `rate-limited` + `Retry-After` |
| 在途 HTTP 请求 | user_id | 32 | 429 `too-many-requests` + `Retry-After: 1` |
| 并发 WebSocket | user_id | 4 | 429 `too-many-sockets`（升级握手中返回） |
| 身份查询（缓存未命中才调用 FastAPI `/me`） | 客户端地址 | 5/s，突发 20 | 429 `lookup-rate`；已缓存的用户不受影响 |
| 新 Host 启动 | 全局 | 30/min，突发 10 | 429 `host-start-rate` + `Retry-After`；已运行的 Host 不受影响 |

- 突发默认 80、在途 32 是按真实浏览器启动 DSH Web 时约 30 个并行请求定的（插件合并包、静态资源、RPC）。
- 客户端地址默认用 socket 对端；经过 Caddy 时设 `PUREGAMMA_DSH_CLIENT_IP_HEADER=x-real-ip`。Caddy 只写入 `{client_ip}`，与 API 站点同一规则。
- 各键之间完全独立。唯一共享的预算是全局 Host 启动速率，而且只有需要新 Host 的请求才会消耗它。
- KeyedBuckets 的键数有上限（默认 5 万）：先丢弃已满的桶，仍超出则丢弃最早的。

### 3.2 审计日志（`src/audit.ts`）

- 每个事件一行 JSON。默认写到 stdout（broker 的普通日志在 stderr）。`PUREGAMMA_DSH_AUDIT=off` 关闭，设为文件路径则以 0600 追加到文件。
- 字段：`ts`、`event`（http/ws/host/revoke/limit）、`action`（`rpc:<插件>/<方法>`、`ws:remote.mux`、`page`、`asset`、`host:start|stop|exit|quota|start-rate`、`revoke`）、`user`、`session`、`plugin`、`provider`、`trace`、`result`、`status`、`ms`。
- `user`：用 broker 密钥派生的 HMAC-SHA256 取前 24 位十六进制。user_id 本身可以猜测（来自 API 的 UUID），普通哈希能被持有日志的人确认，所以用带密钥的哈希。不写 email、cookie、Authorization、Host token、launch token。
- `session`/`provider`：只对 RPC JSON 请求（≤64 KB）在请求或响应结束后做**标识符扫描**：取第一个 `sessionId`，以及 `provider`/`providerId` 字符串，并按格式校验。请求体和响应体的其他内容（prompt、工具输出、标题）不保留，查询串和请求头也不写。
- `trace`：接受合法的 W3C `traceparent`（拒绝全零 trace id），否则接受 `X-Request-Id`（`[A-Za-z0-9._:-]{1,128}`），都没有就生成。转发给 Host 的是同一个 trace id 加新的 span id，以及 `X-Request-Id`。FastAPI 的 `/me` 和 Host token 签发请求也带上这两个头，响应头回传 `X-Request-Id`。
- 静态资源成功请求默认不记（`PUREGAMMA_DSH_AUDIT_ASSETS=true` 才记）；被拒绝的请求一律记录。
- 能看到什么：HTTP RPC 级别。WebSocket mux 只记录打开/关闭（包括关闭原因和时长），mux 内的帧不解析。Host 调 FastAPI（legacy-api provider）时还不透传 trace，列入遗留。

### 3.3 登出联动

| 方案 | 评估 |
| --- | --- |
| 只缩短 `/me` 缓存 | 每个请求都打 FastAPI；而且**已打开的 WebSocket 隧道根本不会再次检查**（v0.3.3 的缺口：用户登出后隧道一直可用） |
| FastAPI 主动通知 broker（已实现，默认关闭） | `DSH_BROKER_REVOKE_URL` 配置后，`/auth/logout` 在响应发出后以后台任务 POST `{"user_id"}`（附 `X-PureGamma-Broker-Secret`，超时 2 s，不跟随重定向）。broker 收到后：清除该用户所有缓存身份、关闭该用户全部 WebSocket、停止其 Host（同时删除 token 文件），返回 204。通知失败只记日志，不影响登出 |
| broker 定期复查已打开的隧道（已实现，默认开） | 每 `PUREGAMMA_DSH_SOCKET_REVALIDATE_MS`（默认 60 s）用隧道建立时的凭证经过同一缓存重新查一次 `/me`，查不到或用户变了就关闭（原因记为 `revalidation-failed`）。所有 `session_version` 递增（登出、在其他设备登录）都会在“缓存 TTL + 复查间隔”内生效；FastAPI 不可用时保持连接，只记日志，不会一次断开所有人 |

- `/__broker/revoke` 和 `/__broker/healthz` 在 Caddy 站点中一律 404（`@broker_internal`）。FastAPI 直接访问 broker 的内部地址；broker 自己也用常量时间比较校验密钥（≥32 字符），只接受 POST，请求体不超过 1 KB。

## 6. 开关汇总（全部默认关闭或采用安全值）

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `PUREGAMMA_DSH_BROKER_ENABLED`（v0.3.3） | `false` | broker 不是 `true` 不启动 |
| `PUREGAMMA_DSH_BASE_PATH` | 空（根路径） | 前缀挂载；必须形如 `/harness` |
| `PUREGAMMA_DSH_CSP` | 见 1.4 | 覆盖默认 CSP；空串表示不发送 |
| `PUREGAMMA_DSH_LOGIN_URL` | 空 | 未登录导航的 401 页面里的登录链接；只接受 http(s) |
| `HARNESS_DOMAIN` / `DSH_BROKER_UPSTREAM`（compose override） | 无（必填） | 只有使用 `docker-compose.harness-sessions.yml` 时才需要 |
| `NEXT_PUBLIC_DSH_SESSIONS_URL`（web 构建期） | 空 | 设置后聊天页头出现入口链接 |
| `PUREGAMMA_DSH_HOST_LAUNCHER` | `direct` | `direct` / `systemd` / `docker` |
| `PUREGAMMA_DSH_INSTANCE` | `default` | unit/容器名前缀与 label；启动时只清理本实例的遗留 Host |
| `PUREGAMMA_DSH_HOST_MEMORY_MB` | 堆上限 + 512（默认 1536） | systemd/docker 的内存上限，至少比堆上限多 128 MB |
| `PUREGAMMA_DSH_HOST_CPU_PERCENT` / `_TASKS_MAX` / `_NOFILE` / `_FILE_SIZE_MB` | 100 / 256 / 4096 / 256 | CPU、进程数、文件描述符、单文件大小 |
| `PUREGAMMA_DSH_HOST_DISK_MB` / `_DISK_CHECK_MS` | 1024 / 60000 | 用户目录配额（所有 launcher）/ 运行中复查间隔 |
| `PUREGAMMA_DSH_SANDBOX_RO_PATHS` | 空 | systemd/docker 额外的只读路径 |
| `PUREGAMMA_DSH_SANDBOX_HIDE` | `/data,/srv,/mnt,/media,/opt` | systemd 下要隐藏的根目录 |
| `PUREGAMMA_DSH_USER_RPS` / `_USER_BURST` | 20 / 80 | 每用户请求速率 |
| `PUREGAMMA_DSH_USER_MAX_INFLIGHT` / `_USER_MAX_SOCKETS` | 32 / 4 | 每用户在途请求 / WebSocket |
| `PUREGAMMA_DSH_IP_LOOKUP_RPS` / `_IP_LOOKUP_BURST` | 5 / 20 | 每个客户端地址的 `/me` 查询（仅缓存未命中时） |
| `PUREGAMMA_DSH_HOST_STARTS_PER_MIN` / `_HOST_START_BURST` | 30 / 10 | 全局新 Host 启动 |
| `PUREGAMMA_DSH_CLIENT_IP_HEADER` | 空（socket 地址） | 经 Caddy 时设为 `x-real-ip` |
| `PUREGAMMA_DSH_AUDIT` / `_AUDIT_ASSETS` | `stdout` / `false` | 审计日志去向 / 是否记录静态资源 |
| `PUREGAMMA_DSH_SOCKET_REVALIDATE_MS` | 60000 | 已打开隧道的复查间隔（0 = 关闭） |
| `DSH_BROKER_REVOKE_URL`（API） | 空 | 登出时通知 broker；还需要 `DSH_MULTI_TENANT_ENABLED=true` 和 ≥32 字符的 `DSH_BROKER_SECRET`；生产校验要求必须是 http(s) |
| `PUREGAMMA_DSH_DOCKER_IMAGE` / `_NODE` / `_NETWORK` / `_USER` / `_ADD_HOSTS` / `_BIN` | 空（docker 必填）/ `node` / `bridge` / broker 的 uid:gid / 空 / `docker` | docker launcher |

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

### 7.2 Host 隔离

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| launcher 单元 + live | `PG_BROKER_DOCKER_IMAGE=python:3.12-slim tsx --test scripts/session-broker-launchers.test.mjs`（已并入 `session-broker-check`；没有 user manager 或镜像时对应 live 例 skip） | 7 passed：默认值与校验；systemd 属性与 docker 参数逐项断言（只有本用户目录可写，密钥值不在 argv 中）；磁盘配额（507、他人不受影响、运行中超限被停）；profile 私有化；systemd live；docker live |
| systemd live（fake Host 内部自检） | 同上 | `pid 1`、可见进程 1 个；hosts 根目录只看到自己；写 hosts 根目录与 `/etc` 返回 `EROFS`；`/data/home` 返回 `ENOENT`；超过 4 MB 的文件返回 `EFBIG`；`memory.max=671088640`、`pids.max=64`、`cpu.max=50000 100000`；nofile 1024；NoNewPrivs=1；CapEff=0；unit 在 `pgdsh.slice`；空闲回收与崩溃后重启时 unit 都被清除 |
| docker live（fake Host 内部自检） | 同上 | 可见进程 3 个（tini、入口、Host）；只看到自己的目录；写 hosts 根目录返回 `EACCES`、写 `/etc` 返回 `EROFS`；`EFBIG`；cgroup 与 rlimit 值同上；CapEff=0；空闲回收后容器被删除 |
| 真实 DSH（systemd） | `PG_BROKER_IT_LAUNCHER=systemd PG_BROKER_IT_BROWSER=1 PG_BROKER_IT_HOST_HEAP_MB=384 … session-broker.integration.mjs` | `# pass 12 / # fail 0`：原有 9 项 + unit 属性（MemoryMax=939524096、TasksMax=128、CPUQuota 1s、NOFILE 2048、FSIZE 64 MB、NoNewPrivileges、ProtectSystem=strict）+ 通过 `/proc/<pid>/root` 确认每个 Host 只看到自己的目录、`/data/home` 不存在 + 浏览器（27 个请求 + 1 个 WebSocket，0 错误）+ 空闲回收 |
| 真实 DSH（docker，`python:3.12-slim` + 只读挂载宿主 node） | `PG_BROKER_IT_LAUNCHER=docker PG_BROKER_IT_DOCKER_IMAGE=python:3.12-slim …` | `# pass 12 / # fail 0`：`docker inspect` 中 Memory、NanoCpus、PidsLimit=128、ReadonlyRootfs、CapDrop ALL、no-new-privileges、ulimits 都符合；`docker exec` 确认只看到自己的目录；浏览器 0 错误；空闲回收 |
| 真实 DSH（direct，回归） | 不设置 launcher | `# pass 10 / # fail 0`，共享 `harness/profile/cordis.yml` 不再被修改 |

变异测试：

| 变异 | 结果 |
| --- | --- |
| systemd 不隐藏 hosts 根目录 | systemd live 失败 |
| systemd 去掉 MemoryMax/TasksMax | 属性测试与 live 测试都失败 |
| docker 把整个 hosts 根目录 rw 挂载 | 参数测试与 docker live 都失败 |
| 恢复 v0.3.3 的共享 profile 软链接 | profile 私有化测试失败 |
| 启动前不检查配额 | 配额测试失败 |
| docker 去掉 `--read-only`/`--cap-drop` | 参数测试失败 |

### 7.3 速率限制、审计、登出

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| broker 单元 | `tsx --test scripts/session-broker-limits.test.mjs`（已并入 `session-broker-check`） | 8 passed：令牌桶/键数上限/并发计数；每用户速率 429 + Retry-After 且 B 为 200；在途请求与 WebSocket 上限（释放后恢复，B 不受影响）；按地址限制 `/me` 洪泛（已缓存用户和其他地址不受影响）；全局 Host 启动速率（已运行的 Host 不受影响）；审计字段，以及不含 cookie/用户 id/token/prompt/密钥/`@`；traceparent 同 trace 新 span、X-Request-Id 透传到 Host 与 FastAPI；revoke（错误密钥 403、GET 405、空 body 400、成功 204，关闭隧道、停止 Host、清缓存，B 不受影响）；隧道复查关闭已登出用户的连接 |
| Caddy | `ingress-check` | `/__broker/healthz` 与 `/__broker/revoke` 经边缘返回 404，请求不到达 broker |
| API | `pytest tests/security/test_dsh_broker_revoke.py tests/security/test_dsh_host_tokens.py tests/test_auth.py tests/security/test_production_configuration.py` | 47 passed（新增 6 例：默认不通知；只配 URL 而多租户关闭时不生效；只发送 user_id 与密钥，超时 ≤2 s，不跟随重定向；broker 失败不影响登出；对本地 HTTP 桩的线上格式（204 成功、403 失败）；生产拒绝非 http(s) URL） |
| ruff | CI 子集 `--select E9,F63,F7,F82`；新文件全规则 | 通过 |
| 真实 DSH（direct） | `PG_BROKER_IT_BROWSER=1 … session-broker.integration.mjs` | `# pass 13 / # fail 0`：并发 150 个 A 的 `session/list` → `{"200":65,"429":85}`，同时 B 为 200，4 s 后 A 恢复；178 行审计，rename 行带 `session-…` 与 `plugin: session`，不含会话标题、cookie 或 token；revoke 关闭 B 的真实 WebSocket 并停止 B 的 Host，A 不受影响；浏览器启动正常（默认限额不影响页面加载） |

变异测试（每项单独做，恢复后 8/8 通过）：去掉每用户速率检查、所有用户共用一个桶、去掉在途上限、revoke 不校验密钥、复查不关闭隧道、审计写原始 user_id、去掉 `/me` 查询闸门——各自对应的测试都失败。
