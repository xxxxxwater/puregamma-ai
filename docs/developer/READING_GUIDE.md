# 阅读框架 / Reading Guide

> **这份文档写给谁**：刚接手这个仓库、需要在几天内读懂代码的工程师。
> **它不做什么**：不复述架构图。`docs/developer/ARCHITECTURE.md` 已经有 mermaid 架构图和各层的职责表，本文件只回答两个问题——**哪里是真的**、**从哪读起**。
> **准确性**：本文件里的路径、端点、命令行输出都在仓库或生产主机上实际核对过（核对日期见文末）。凡是没核对过的推断，都显式写成「未核对」。

**English summary.** This is an onboarding reading guide, not another architecture diagram (`docs/developer/ARCHITECTURE.md` already owns that). It answers two questions only: *what here is real*, and *where to start reading*. Every path, endpoint and shell command below was verified against the repository or the production host on the date noted at the end. Anything inferred rather than verified is labelled as such.

---

## 0. 先读这五条真相（30 秒版）

1. 这是一个 **多应用 monorepo**：Python 后端 + Next.js 前端 + Android/iOS 原生壳 + 一个独立的 pocket-relay 服务，共享代码全在 `packages/`。
2. 后端分层是 **router（HTTP）→ service（业务）→ packages（领域）**，`apps/api/routers/*.py` 里的函数应该只做参数校验和编排。
3. 数据库访问是 **同步 SQLAlchemy**（`SessionLocal` + `Depends(get_db)`），不是 async ORM。看到 `db.query(...)` 不要找 `await`。
4. **线上跑的不是你本地这份工作树。** 生产主机上真正被执行的是 `/puregamma/build-<tag>/` 目录（见第 5 节）。`/puregamma/app/` 是 compose 文件和 `.env` 的所在地，不一定是代码。
5. 仓库里 **CRLF 和 LF 混用**，而且没有 `.gitattributes`。改文件前先看该文件基线用什么行尾（见第 6 节）。

**English summary.** Five facts up front: (1) a multi-app monorepo with shared domain code in `packages/`; (2) backend layering is router → service → packages; (3) database access is *synchronous* SQLAlchemy, so `await` will never appear next to `db.query(...)`; (4) production does **not** run your working tree — it runs code from `/puregamma/build-<tag>/` directories, while `/puregamma/app/` holds the compose files and `.env`; (5) CRLF and LF are mixed in the repository with no `.gitattributes`, so check a file's baseline before editing.

---

## 1. 这个仓库是什么

一句话：**PureGamma AI 是一套量化研究 + 投资组合复盘产品**——它产出研究报告、信号、每日简报、NAV 估算和回测，通过 Web / 移动端 / iMessage 交付；它**不下单**（LIVE 交易控制面存在，但生产环境的所有闸门默认关闭，见第 6 节）。

仓库里的四类东西，读代码时务必分清：

| 类别 | 例子 | 是否需要读懂 |
| --- | --- | --- |
| 产品代码 | `apps/api/`、`apps/web/`、`packages/` | 是，主线 |
| 移动端壳 | `apps/android/`、`apps/ios/` | 只读 `ApiClient` / `Core`，其余是平台细节 |
| 辅助服务 | `apps/pocket-relay/`、`apps/imessage-relay/` | 独立小服务，各读 `main.py` 即可 |
| 过程产物 | `tests/`、`scripts/`、`deploy/`、`docs/`、`releases/` | 按需，`docs/developer/` 优先 |

**English summary.** PureGamma AI is a quant research and portfolio-review product: research, signals, daily briefs, NAV estimates and backtests, delivered over web, mobile and iMessage. It does not place trades in the production baseline. Four kinds of content coexist: product code (the main line), mobile shells (read only their API client), small auxiliary services (read `main.py`), and process artifacts (tests, scripts, deploy, docs — `docs/developer/` first).

---

## 2. 目录地图

### 2.1 应用（`apps/`）

| 目录 | 职责 | 从哪个文件读起 |
| --- | --- | --- |
| `apps/api/` | FastAPI 后端。41 个 router、44 个 service | `apps/api/main.py`（277 行，看 middleware 和 `include_router` 顺序） |
| `apps/web/` | Next.js 前端（App Router + i18n，89 个 `page.tsx`） | `apps/web/lib/api.ts`（2589 行，前端唯一 API 客户端） |
| `apps/android/` | Android 壳：WebView + 原生 push/OAuth。源码在 `apps/android/app/src/main/java/ai/puregamma/android/` | `MainActivity.kt` → `ui/WebProductScreen.kt` → `core/ApiClient.kt` |
| `apps/ios/` | iOS 壳，Swift Package 风格目录 | `apps/ios/PureGamma/App/` 与 `Core/` |
| `apps/pocket-relay/` | 独立 FastAPI 服务：手机扫码 + 8 位密码访问同一套 web，含 cloudflared 隧道 | `apps/pocket-relay/main.py`，再读 `README.md` |
| `apps/imessage-relay/` | macOS 上通过 AppleScript 驱动 Messages.app 的中继 | `apps/imessage-relay/relay.py`、`inbound.py` |
| `apps/site/` | 独立的营销站（Next.js + Drizzle） | `apps/site/README.md`，与主产品无关，可跳过 |

### 2.2 共享包（`packages/`，24 个）

| 目录 | 职责 | 从哪个文件读起 |
| --- | --- | --- |
| `packages/database/` | SQLAlchemy models、session、seed、Alembic 迁移（33 个版本，head = `0032_chat_workspace`） | `packages/database/session.py` → `models.py`（2687 行，按 `__tablename__` 跳读） |
| `packages/agents/` | Agent 编排：research、market、risk、strategy、report、chat | `packages/agents/llm/provider_factory.py` |
| `packages/agents/llm/` | **LLM 抽象层**：`LLMProvider`（`base.py`）的 4 个实现——deepseek / openai / kimi / mock | `packages/agents/llm/base.py` → `provider_factory.py` |
| `packages/data/` | 外部数据源 provider（Coingecko、Glassnode、Plaid、IBKR、Hyperliquid、EVM…） | `packages/data/base.py` |
| `packages/trading/` | 交易领域模型：domain、events、permissions、policies、states | `packages/trading/domain/` |
| `packages/live_trading/` | LIVE 控制面：control_plane、kill_switch、ledger、nav、reconciliation、risk_engine、secret_store | `packages/live_trading/flags.py`（所有闸门都在这里） |
| `packages/risk/` | 风险计算：drawdown、position_sizing、scoring、engine | `packages/risk/engine.py` |
| `packages/security/` | 密码哈希（scrypt）等安全原语 | `packages/security/passwords.py` |
| `packages/gateway/` | 对外 LLM API 网关：catalog、pricing、registry、security、usage | `packages/gateway/service.py` |
| `packages/harness/` | 研究报告 harness：adapter、composition、state_machine、versions | `packages/harness/state_machine.py` |
| `packages/workers/` | Celery app、APScheduler 调度、任务、Redis 锁 | `packages/workers/celery_app.py` → `scheduler.py` |
| `packages/backtest/`、`packages/strategies/`、`packages/options/`、`packages/nautilus/` | 回测引擎、策略、期权面、Nautilus 运行时对接 | 各自的 `__init__.py` 与同名入口模块 |
| `packages/billing/`、`packages/capabilities/`、`packages/notifications/`、`packages/reports/`、`packages/memory/`、`packages/skills/`、`packages/research_runner/`、`packages/config/` | 计费与积分、能力门、通知渠道、报告渲染、记忆、技能、研究运行器、密钥存取 | 按需 |

### 2.3 其他

| 目录 | 职责 | 从哪个文件读起 |
| --- | --- | --- |
| `tests/` | 136 个 `test_*.py`：`unit/`、`integration/`、`e2e/`、`security/`、`acceptance/`、`load/`、`quant/`、`gateway/`、`workers/` | `tests/conftest.py`，然后挑一个和你任务同域的测试 |
| `deploy/` | 部署与发布脚本（rsync、release-*、rollback） | `deploy/release-build-chat-workspace.sh`（同时是部署真相的说明书） |
| `scripts/` | 一次性脚本：`db_migrate.py`、`validate-production-env.py`、`production-smoke.sh`、`probe_chat_workspace.py` | `scripts/db_migrate.py` |
| `docs/developer/` | 开发者文档：`ARCHITECTURE.md`、`API_REFERENCE.md`、`DATABASE_SCHEMA.md`、`LLM_PROVIDER_ARCHITECTURE.md` 等 | `ARCHITECTURE.md` |
| `docs/deployment/`、`docs/live-trading/`、`docs/release/` | 部署、LIVE 交易、发布与回滚 | `docs/deployment/DEPLOYMENT_OVERVIEW.md` |
| `config/`、`services/nautilus-runtime/` | YAML 配置、nautilus runtime 服务 | `config/` 下的 yaml + `services/nautilus-runtime/Dockerfile` |
| `docker-compose.production.yml` | 生产 compose：8 个 service（postgres、redis、nautilus-runtime、api、worker、scheduler、pocket、web、caddy）+ 7 个 volume + 4 个 network | 本文件本身 |

**English summary.** `apps/` holds the FastAPI backend (41 routers, 44 services — start at `apps/api/main.py`), the Next.js frontend (start at `apps/web/lib/api.ts`), two thin mobile shells, and two small standalone services (`pocket-relay`, `imessage-relay`). `packages/` holds 24 shared domain packages; the ones you cannot avoid are `database`, `agents` (whose `llm/` subpackage is the full LLM abstraction), `data`, `workers` and `live_trading`. `tests/` has 136 test files, `deploy/` documents the real release mechanism, and `docker-compose.production.yml` defines 8 services.

---

## 3. 后端请求的阅读路径

用一个**真实存在、端到端有写库**的例子把链路串起来：`POST /portfolio/accounts/{account_id}/sync`（用户点「同步账户」）。

```
① Caddy 容器 (edge)               Caddyfile                                  反向代理 + TLS，同时决定 X-Real-IP
② apps/api/main.py:129 request_trace     生成/透传 X-Request-ID，记 request_completed
③ apps/api/main.py:90  rate_limit        只有 production 生效；按 x-real-ip 分桶（Redis pg:rate:*）
④ apps/api/main.py:71  cookie_csrf_guard 带 session cookie 的写请求必须来自 CORS_ORIGINS 里的 Origin
⑤ apps/api/routers/portfolio.py:526      sync_connected_account()
                                         依赖注入：Depends(get_db) + Depends(get_current_user)
⑥ apps/api/dependencies.py:75  get_db            → SessionLocal()
   apps/api/dependencies.py:83  get_current_user → verify_access_token() → db.get(User, sub) → 校验 session_version
⑦ apps/api/services/portfolio_service.py:406 sync_account()
                                         按 account.venue 分派：HYPERLIQUID / EVM / PLAID / IBKR / BINANCE|OKX|BYBIT
   apps/api/services/portfolio_service.py:456 _sync_hyperliquid()
                                         外部 HTTP 拉数据 → 组装 positions 列表
   apps/api/services/portfolio_service.py:1378 _save_snapshot()
                                         db.add(AccountSnapshot(...)) + db.add(PositionSnapshot(...)) + db.commit()
⑧ packages/database/models.py:1553 AccountSnapshot / :1533 PositionSnapshot   真实落地表：account_snapshots / position_snapshots
⑨ apps/api/services/portfolio_service.py:544 portfolio_view(db, user)        读回视图 → JSON 返回前端
```

读这条链路时要抓住的四件事：

- **入口只有一个**：所有 router 都在 `apps/api/main.py` 第 229–277 行注册。想知道某个 URL 属于哪个 router，看那里的 `include_router`（注意 `agent`、`secretary`、`skills`、`research`、`research_runner`、`harness_runs`、`memory` 带 `prefix="/api"`）。
- **中间件顺序即执行顺序**：`cookie_csrf_guard` → `rate_limit` → `request_trace`（FastAPI 后注册的先进入，实际顺序以 `main.py` 为准）。限流和 CSRF 都只在 `APP_ENV=production` 生效。
- **鉴权有两种入口**：`Authorization: Bearer`，或 `settings.session_cookie_name`（默认 `pg_session`）cookie。`verify_access_token` 是自己实现的 HS256 JWT（`dependencies.py:31`），不是 python-jose。
- **db 生命周期**：`get_db()` 是 generator，`finally: db.close()`；service 层自己 `db.commit()`（见 `sync_account` 的 `except` 分支：失败时 `rollback` 并把 `ExchangeConnection.status` 置为 `ERROR`，而不是抛裸异常给前端）。

配置也在这一层：`apps/api/config.py` 是一个 **frozen dataclass**，每个字段用 `os.getenv(...)` 读环境变量，`get_settings()` 被 `@lru_cache` 缓存（第 759 行）——所以**改环境变量不会热生效**，必须重启进程。`validate_production_settings()`（第 764 行）在 import main.py 时就跑，生产环境配置不合格会直接 `RuntimeError` 拒绝启动。

另外两个真实存在的入口，别漏：

- **异步任务**：`packages/workers/celery_app.py`（Celery，broker/backend 都是 Redis） + `packages/workers/scheduler.py`（APScheduler，**只负责 send_task，不执行重活**）。
- **网关**：`packages/gateway/` 是一套独立的 OpenAI 兼容 API 网关（`gateway.openai_router`），不是 Agent 用的 LLM 抽象。

**English summary.** Trace one real write-path request, `POST /portfolio/accounts/{account_id}/sync`: Caddy → `main.py` middlewares (`request_trace`, `rate_limit`, `cookie_csrf_guard`) → `routers/portfolio.py:526` → injected `get_db` / `get_current_user` from `dependencies.py` → `services/portfolio_service.py:406 sync_account` → `:456 _sync_hyperliquid` → `:1378 _save_snapshot` which writes `AccountSnapshot` / `PositionSnapshot` (`packages/database/models.py:1553` / `:1533`) → `portfolio_view()` reads back the JSON. Every router is registered in `apps/api/main.py:229-277` — that block is the URL map. Settings are a cached frozen dataclass reading `os.getenv`, so env changes need a process restart, and `validate_production_settings()` fails startup loudly on a bad production config. Async work lives in `packages/workers/` (Celery + APScheduler); `packages/gateway/` is a separate OpenAI-compatible API gateway, not the agent LLM abstraction.

---

## 4. 前端阅读路径

仍用 portfolio 这个页面把链路串起来（`apps/web/app/[locale]/portfolio/page.tsx`，22 行，它自己不含数据逻辑）：

```
① apps/web/middleware.ts:23 middleware()
     - 跳过 /api、/_next、静态文件
     - 路径没有 (en|zh) 前缀 → 按 cookie(pg_locale) / Accept-Language / 中国 IP 地理判断重定向
     - NEXT_PUBLIC_INITIAL_LAUNCH_MODE !== "false" 时隐藏一批路由（INITIAL_LAUNCH_HIDDEN）
     - REQUIRE_AUTH === "true" 且路由需要登录且没有 pg_session cookie → 跳 /{locale}/login?returnTo=...
② apps/web/app/[locale]/layout.tsx            按 locale 组装 shell
③ apps/web/app/[locale]/portfolio/page.tsx    Server Component：generateMetadata() + <PortfolioConsole locale={...} />
④ apps/web/components/portfolio-console.tsx   Client Component（"use client"）：useState/useEffect 管理全部状态
⑤ apps/web/lib/api.ts:1073 getPortfolioSnapshot() → api<T>("/portfolio")
   apps/web/lib/api.ts:1378 requestStrict()        → fetch，credentials: "include"，401 触发 notifyAuthExpired()
⑥ FastAPI apps/api/routers/portfolio.py:207 get_portfolio()
```

读前端时必须知道的六点：

- **`apps/web/lib/api.ts`（2589 行）是唯一 API 客户端。** 不要在组件里直接 `fetch`。大多数读接口用 `api<T>(path, { fallback })`——后端挂了会拿到 `fallback` 并渲染降级视图；写接口用 `requestStrict`，失败会抛带 `status` 的 `Error`。
- **URL 不是硬编码的。** `NEXT_PUBLIC_API_URL` 可以是绝对地址（生产是 `https://api.puregamma.ai`），也可以是同源路径（开发代理 `/__dev-api`）。Client Component 用 `apiBaseUrl()`；Server Component 有 origin 问题，必须 `await resolveApiUrl()`（`api.ts:56`）。WebSocket 走 `apiWebSocketBaseUrl()`。
- **跨域 cookie 靠转发头。** 浏览器请求打到 API 域名时会带不上 cookie，所以 `requestStrict` 先取 `forwardedSessionHeaders()` 再把会话头显式带上。
- **i18n 是硬要求。** 文案在 `apps/web/messages/`，组件里写死的中文/英文只作为兜底；路由是 `[locale]` 段（`en` / `zh`，默认 `en`）。
- **登录后的会话是 cookie（`pg_session`），不是 localStorage。** 请求一律 `credentials: "include"`。
- **`apps/web/app/api/` 下有一层 Next.js route handlers**，它们不是主 API，只是给浏览器的薄代理/助手。真正业务在 FastAPI。

**English summary.** The frontend flow for the portfolio page: `middleware.ts` resolves the locale prefix (cookie → Accept-Language → geo for the landing page only), enforces the initial-launch hidden routes, and redirects unauthenticated visitors when `REQUIRE_AUTH=true`; `app/[locale]/portfolio/page.tsx` is a Server Component that renders the Client Component `components/portfolio-console.tsx`; all data goes through `lib/api.ts` — `getPortfolioSnapshot()` (a read with a `fallback`) or `requestStrict()` (a write that throws with `status`, and notifies on 401). `NEXT_PUBLIC_API_URL` may be absolute or a same-origin dev-proxy path, so server code must `await resolveApiUrl()` while client code uses `apiBaseUrl()`. Auth is a `pg_session` cookie, never localStorage.

---

## 5. 部署真相（重点）

这一节的目的只有一个：**让你能自己回答「线上正在跑的是哪份代码」。**

### 5.1 生产主机

| 项 | 值 |
| --- | --- |
| 主机 | 阿里云 ECS（Alibaba Cloud），远程主机，`hostname` = `iZ6we7ww5k8vfwe8bnd99hZ` |
| 地址 | `47.245.55.228`，以 **root** 通过 SSH 登录 |
| SSH key | `~/Desktop/puregamma.ai/vscode_DEEPSEEKV4_new.pem`（写在 `deploy/deploy-phase5.sh:15`；可用 `PG_KEY` 环境变量覆盖） |
| 公网站点 | `https://app.puregamma.ai`（web）、`https://api.puregamma.ai`（api），由 Caddy 容器终止 TLS |

### 5.2 代码是怎么上去的：**不是 git**

这是最容易踩错的一点。服务器上**没有**用于部署的 git 工作副本，代码是**从一台 macOS 工作树用 rsync 推上去的**：

```bash
# deploy/deploy-phase5.sh 的核心三行（已经核对，见该脚本 15-20、64-71 行）
SRC="$HOME/Desktop/puregamma.ai/puregamma-ai/"
DST="root@$HOST:/puregamma/app/"
rsync -az --progress "${EXCLUDES[@]}" -e "$RSH" "$SRC" "$DST"
```

要点：
- rsync **不带 `--delete`**，服务器独有文件不会被删；
- `.git`、`.env*`、`node_modules`、`.venv*`、`__pycache__`、`*.db`、`releases/` 等被显式排除；
- 部署脚本随后在 `/puregamma/app` 里 `docker compose build` + `up -d`，**不**用 `down -v`（数据库卷保留），并在部署前 `pg_dump` 到 `/puregamma/backup/`。

### 5.3 `/puregamma/app/.git` 是一个**损坏的 worktree 指针**

`/puregamma/app/.git` 不是一个目录，而是一个**文本文件**，内容是一行：

```
gitdir: /Users/christse/Desktop/puregamma.ai/puregamma-ai/.git/worktrees/code
```

也就是说它指向的是 **Mac 上的 worktree 目录**（git 把主仓库和 worktree 的元数据放在 `.git/worktrees/<name>/`，rsync 把这个指针文件带上了服务器）。后果已经在生产主机上实测：

```
$ cd /puregamma/app && git status
fatal: not a git repository: /Users/christse/Desktop/puregamma.ai/puregamma-ai/.git/worktrees/code
$ echo $?
128
```

**结论：在 `/puregamma/app` 里跑任何 git 命令都没有意义**，也不要相信 `docs/release/2.2/ROLLBACK.md`、`docs/live-trading/ROLLBACK.md` 里 `cd /puregamma/app && git log/checkout` 那几段命令——对当前这台主机它们不成立。

### 5.4 `/puregamma/.git-mirror` 是 bare **fetch-only** 镜像

```
$ git --git-dir=/puregamma/.git-mirror config --get remote.origin.url
https://github.com/xxxxxwater/puregamma-ai.git
$ git --git-dir=/puregamma/.git-mirror log --oneline -3
fatal: your current branch 'master' does not have any commits yet
$ git --git-dir=/puregamma/.git-mirror for-each-ref --format='%(refname)'
refs/remotes/origin/main
refs/remotes/origin/release/2.2-predeploy
... （只有 refs/remotes/origin/* 和 tags，没有本地分支提交）
```

它是一个**只有远端 ref 的镜像**，**没有本地提交**。它的用途是 `git archive` 导出**某个确切 commit** 的源码树去构建镜像——也就是 `deploy/release-build-chat-workspace.sh` 的做法：先 `fetch`，断言 mirror 的 `refs/remotes/origin/main` 前缀等于你要求的 short SHA（不等就拒绝构建），再 `git archive <sha> | tar -x -C /puregamma/build-<sha>`，最后用 `git hash-object` 逐文件证明导出的树等于 commit blob。

**所以存在两条并存的部署路径**：老的 rsync → `/puregamma/app/`，和新的 mirror-archive → `/puregamma/build-<sha>/`。当前生产主要走后者。

### 5.5 容器 → 目录映射（**这是排查「线上是哪份代码」的可靠方法**）

`docker inspect` 的 `com.docker.compose.project.working_dir` label 记录了某个容器是**在哪个目录里被 compose 起来的**：

```
容器                                working_dir                              image
puregamma-ai-web-1                  /puregamma/build-pmui7-20260916          puregamma-ai-web:pmui7-20260916
puregamma-ai-api-1                  /puregamma/build-pmui3-20260916          puregamma-ai-api:pmui3-20260916
puregamma-ai-worker-1               /puregamma/build-0dbe7b48                puregamma-ai-worker:0dbe7b48
puregamma-ai-scheduler-1            /puregamma/build-0dbe7b48                puregamma-ai-scheduler:0dbe7b48
puregamma-ai-pocket-1               /puregamma/build-mobile1-20260916        puregamma-ai-pocket:mobile1-20260916
puregamma-ai-caddy-1                /puregamma/app                           caddy:2-alpine
puregamma-ai-postgres-1             /puregamma/app                           postgres:16
puregamma-ai-redis-1                /puregamma/app                           redis:7-alpine
puregamma-ai-nautilus-runtime-1     /puregamma/app                           puregamma-ai-nautilus-runtime
```

排查命令（一条查清楚一个容器）：

```bash
# 在服务器上执行；把 <container> 换成 puregamma-ai-web-1 等
docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'
```

一次列出所有容器，得到上面那张表：

```bash
for c in $(docker ps --format '{{.Names}}'); do
  printf '%-34s %-42s %s\n' "$c" \
    "$(docker inspect "$c" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')" \
    "$(docker inspect "$c" --format '{{.Config.Image}}')"
done
```

从这张表能直接读出三条不能靠猜的结论：

1. **web / api / worker / scheduler / pocket 都不跑 `/puregamma/app` 里的代码**，它们跑的是各自的 `build-*` 目录。只有 caddy / postgres / redis / nautilus-runtime 的 working_dir 是 `/puregamma/app`（因为 compose 文件放在那里）。
2. **四个服务的代码版本可以彼此不同。** 上面这一份快照里 web 是 `pmui7-20260916`，api 是 `pmui3-20260916`，worker/scheduler 是 `0dbe7b48`，pocket 是 `mobile1-20260916`——**四个不同的构建**。「我看到线上是这个行为」不能推出「四个服务都是这个版本」。
3. **镜像 tag 不总是 commit SHA。** 有 `<short-sha>` 形式（`0dbe7b48`），也有 `<轮次>-<日期>` 形式（`pmui7-20260916`、`mobile1-20260916`）。**tag 不是证据**，`/puregamma/release-manifest.json` 自己也这么写明（`"authority": "... image TAGS are not treated as evidence"`）。要证明线上跑的代码，用镜像 ID 或进容器 `grep` 源码。

### 5.6 两个容易误判的辅助文件

- **`/puregamma/release-manifest.json` 不是实时状态，是一份历史发布记录。** 实测：文件里写 web 是 `puregamma-ai-web:0dbe7b48`，而同一时刻线上容器是 `puregamma-ai-web:pmui7-20260916`。把它当「上一轮发布干了什么」读可以，当「现在跑什么」读会错。
- **`/puregamma/app/docker-compose.v41-override.yml` 里的 per-service pin 也可能已经过期。** 我读到的 `build-pmui7-20260916/docker-compose.v41-override.yml` 里 api/worker/scheduler/web 全都 pin 到 `0dbe7b48`，但同一目录里的 web 容器实际跑 `pmui7-20260916`。**永远以第 5.5 节的 `docker inspect` 结果为准。**

### 5.7 生产 compose 的服务与网络

`docker-compose.production.yml` 定义 8 个 service：`postgres`、`redis`、`nautilus-runtime`、`api`、`worker`、`scheduler`、`pocket`、`web`、`caddy`。
- `worker` 的命令是 `celery -A packages.workers.celery_app.celery_app worker`；`scheduler` 是 `python -m packages.workers.scheduler`。
- 有 4 个 network：`edge`（对外）、`data`（`internal: true`，只有 api/worker/postgres/redis 在内）、`runtime`。**api 容器里没有 `docker.sock`**（故意如此，注释写明「一个被打穿的公网容器绝不能碰到宿主机 docker」）。
- 数据库和 Redis 都不发布端口，只在 compose 网络内可达。

**English summary.** Production is a remote Alibaba Cloud ECS host (`47.245.55.228`, `hostname` `iZ6we7ww5k8vfwe8bnd99hZ`) reached over SSH as root. Code is **not** deployed with git: `deploy/deploy-phase5.sh` rsyncs a macOS working tree into `/puregamma/app/` (no `--delete`, `.git` and `.env*` excluded) or, in the newer path, `git archive`s an exact commit out of the bare fetch-only mirror `/puregamma/.git-mirror` into `/puregamma/build-<sha>/`. `/puregamma/app/.git` is a **broken worktree pointer** to a path on the developer's Mac, so `git status` there exits 128 — running git in that directory is meaningless. The live containers do **not** run `/puregamma/app`: the reliable way to learn which code a container runs is

`docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'`

which resolves the live set to web → `build-pmui7-20260916`, api → `build-pmui3-20260916`, worker/scheduler → `build-0dbe7b48`, pocket → `build-mobile1-20260916`, while caddy/postgres/redis/nautilus-runtime run from `/puregamma/app`. The four application services can be on four different builds, image tags are sometimes a commit SHA and sometimes `<round>-<date>` (and are explicitly *not* authoritative), and `/puregamma/release-manifest.json` plus `docker-compose.v41-override.yml` are historical records that can already disagree with the running containers.

---

## 6. 读代码时的坑

### 6.1 CRLF / LF 混用，且没有 `.gitattributes`

仓库**没有** `.gitattributes`（已确认不存在），所以 git 不会帮你做任何行尾归一化，文件中既有的行尾被原样提交。实测统计（`git ls-files --eol`）：

| 范围 | CRLF（index） | LF（index） |
| --- | --- | --- |
| 全部已跟踪文件 | 513 | 768 |
| `*.py` | 370 | 140 |
| `*.ts` / `*.tsx` | 24 | 242 |
| `*.md` | 11 | 209 |

还有 **16 个文件是 mixed**（同一个文件里两种行尾都有），例如 `apps/api/services/daily_brief_service.py`、`packages/agents/chat/tools.py`、`tests/security/test_production_configuration.py`。

用户侧点名的四个文件，逐个核对结果如下（`i/` = git index，`w/` = 工作树）：

| 文件 | 实测 |
| --- | --- |
| `apps/api/routers/portfolio.py` | CRLF |
| `apps/api/routers/mobile_auth.py` | CRLF |
| `apps/api/dependencies.py` | CRLF |
| `docker-compose.production.yml` | CRLF |

**顺带修正一个更常见的误判**：不要以为只有上面四个是 CRLF。`apps/api/routers/` 和 `apps/api/services/` 里绝大多数文件都是 CRLF——`apps/api/main.py`、`apps/api/config.py`、`apps/api/routers/auth.py` 全是 CRLF。**`apps/web/` 绝大多数是 LF**（283 个 LF / 24 个 CRLF）。所以「后端是 CRLF 为主、前端是 LF 为主」比记忆四个文件名更可靠。

怎么查任意文件：

```bash
# 单文件：i/ 是 index，w/ 是工作树
git ls-files --eol apps/api/routers/portfolio.py
# i/crlf  w/crlf  attr/                  apps/api/routers/portfolio.py

# 批量筛出 CRLF 的 Python 文件
git ls-files --eol '*.py' | awk '$1=="i/crlf"{print $4}'
```

**规则：改文件时沿用该文件基线已有的行尾。** 对 CRLF 文件做「整体 LF 归一化」会在 diff 里产生整文件假改动，把真实改动淹掉。已实测的放大比例：一次 **41 行的真实改动** 被整文件行尾归一化放大成 **1155 行 diff**。

如果你的工具（编辑器、prettier、formatter、AI patch 工具）会强制 LF，就先确认它没有偷偷改被改文件的其余行；改完用 `git diff --stat` 看行数是否合理——**行数量级不对就是行尾被改了**，不是你真的改了那么多。

### 6.2 `/puregamma/app` 里那个假的 `.git`

见 5.3。任何 `git` 命令在那里都会 `fatal`，且 `docs/` 里部分 ROLLBACK 文档假设的「`cd /puregamma/app && git log/checkout`」在这台主机上不成立。

### 6.3 「今天线上是哪份代码」不能靠文档回答

文档（`release-manifest.json`、`docker-compose.v41-override.yml`、`docs/release/*`）记的是**发布当时**的事实，可能已经过期。唯一可靠来源是 5.5 的 `docker inspect`，再加「进容器 grep 源码 / 核对镜像 ID」。manifest 的 `artifact_proof` / `live_proof` 字段示范了这个做法（比对容器内 chunk 与线上 chunk 的 sha256）。

### 6.4 prod 配置错误是启动失败，不是运行时报错

`apps/api/main.py:21` 在模块导入时就调用 `validate_production_settings(settings)`。`APP_ENV=production` 时，几十条断言（`JWT_SECRET` 长度、`DATABASE_URL` 不得是 sqlite、`AUTH_ALLOW_DEMO_FALLBACK` 必须 false、Mock provider 必须关、`NAUTILUS_EXECUTION_MODE` 只能是 paper/shadow、LIVE 相关闸门必须为 false …）任一不满足就 `RuntimeError`，容器起不来。排查「API 容器起不来」先看这里。

### 6.5 `get_settings()` 是 `@lru_cache` 的

改了环境变量不重启进程不会生效（`apps/api/config.py:759`）。另注意 `config.py:12`：只有在**非 pytest** 进程里才 `load_dotenv()`，所以测试读的是测试自己设置的环境变量。

### 6.6 数据库访问是同步的，且 `init_db()` 会跑迁移

- `packages/database/session.py` 里 `create_engine(...)` 是同步 engine，`SessionLocal = sessionmaker(bind=engine, ...)`。router 函数大量使用 `def`（同步）而不是 `async def`，这是有意为之，不要「顺手改成 async」。
- `init_db()` → `upgrade_database()` → `alembic upgrade head`，而且 `upgrade_database()` 会在**没有任何 schema 缺口**时把旧库 `stamp` 成 `0001_baseline`；一旦发现缺口就 `fail closed` 抛错。它由 lifespan 里的 `ensure_bootstrap()`（`apps/api/main.py:41`）调用——**API 容器启动即可能改 schema**。

### 6.7 很多「未实现」是刻意的

代码库里大量注释在说明「这里故意不做」。例如 `main.py:264` 注释写明 custody 路由始终注册，没配置凭证时**诚实地返回 `UNCONFIGURED`**，而不是隐藏接口；LIVE 控制面任何闸门不通过就返回 `LIVE_DISABLED`，不伪造数据。把这类「诚实空态」当成 bug 去修，会破坏设计。

### 6.8 一次性脚本会误导

`scripts/` 里有历史探针脚本（`probe_*.py`、`nautilus_spike.py`），有些只对当时那次排查有效。跑之前先读脚本头部注释确认它的前提还成立。同理 `deploy/*.sh` 里有几份是特定轮次的一次性脚本（文件名带 `-chat-workspace`、`-phase5`）。

**English summary.** The pitfalls: (1) CRLF and LF are mixed with no `.gitattributes` — 513 CRLF vs 768 LF overall, 370 CRLF Python files, plus 16 mixed-EOL files; the four files you may have been warned about (`routers/portfolio.py`, `routers/mobile_auth.py`, `dependencies.py`, `docker-compose.production.yml`) are CRLF, but so are most of `apps/api/` including `main.py` and `config.py`, while `apps/web/` is mostly LF. Check with `git ls-files --eol <file>` and **match the file's existing baseline** — normalizing a CRLF file to LF turned a real 41-line change into a 1155-line diff in testing. (2) The fake `.git` in `/puregamma/app`. (3) Documentation about what is deployed goes stale — query the container working_dir label instead. (4) Production config errors fail *startup*, not requests. (5) `get_settings()` is `lru_cache`d. (6) Persistence is synchronous SQLAlchemy and `init_db()` runs `alembic upgrade head` on API startup. (7) Many "unimplemented" paths are deliberate honest empty states (`UNCONFIGURED`, `LIVE_DISABLED`) — don't "fix" them.

---

## 7. 推荐阅读顺序

给你一个能在一两天内建立正确心智模型的顺序。每步都说明**读什么**和**为什么是这一步**。

**第 1 步 — `apps/api/main.py`（277 行，30 分钟）**
为什么第一步就读它：这一个文件同时给你入口框架（FastAPI app + lifespan）、横切关注点（三个 middleware 的语义）、以及**全部 URL 的路由地图**（229–277 行的 `include_router`）。读完你会知道 `apps/api/routers/` 里 41 个文件分别挂在哪个前缀下，后面任何一次跳转都不再靠猜。
注意：它是 CRLF，且 `include_router` 的 `prefix="/api"` 分组不是按字母序排的。

**第 2 步 — `apps/api/dependencies.py`（160 行）+ `packages/database/session.py`（150 行）**
为什么：这两个文件定义了**每一个请求都会经过的东西**——`get_db()` 的 session 生命周期、自己实现的 HS256 JWT（`create_access_token` / `verify_access_token`）、`session_version` 这种「改密码即踢下线」的机制、以及 `init_db()` 会跑 Alembic 迁移这件事。跳过它们，后面读任何 router 都会对「用户是谁」「事务边界在哪」产生错误假设。

**第 3 步 — 一条完整的读链路 + 一条完整的写链路**
读：`routers/portfolio.py:207 get_portfolio` → `services/portfolio_service.py` 的 `portfolio_view`。
写：`routers/portfolio.py:526 sync_connected_account` → `sync_account` → `_sync_hyperliquid` → `_save_snapshot` → `models.py` 的 `AccountSnapshot` / `PositionSnapshot`。
为什么：这两条链把 router → service → packages → 数据库 的分层**在真实代码里**跑通一遍。之后你看任何 router 都能立刻判断「逻辑该在这层还是该下沉到 service」，也能一眼看出 `db.commit()` 归属谁。

**第 4 步 — `packages/database/models.py`（2687 行，按表名跳读）**
为什么：数据模型是产品的真相。不要顺序读；先看 `__tablename__` 列表建立索引，再精读和你任务同域的表。同时打开 `packages/database/alembic/versions/`（33 个版本，head `0032_chat_workspace`），从最新往回看几个迁移，你会知道最近产品在往哪个方向长。

**第 5 步 — `packages/agents/llm/base.py` + `provider_factory.py`（合计约 150 行）**
为什么：这是全仓库被引用最广的抽象，也是误解最多的地方。`LLMProvider` 是**文本补全**抽象（`chat` / `complete` / `structured_json` / `stream_chat`），`get_llm_provider()` 按 `settings.llm_provider` 返回 deepseek / openai / kimi，**任何 provider 未配置就静默降级成 `MockLLMProvider`**（返回 `status="fallback_mock"`）。看到「AI 回答是假数据」时，第一个怀疑对象就是这里，而不是 prompt。

**第 6 步 — `apps/web/lib/api.ts`（2589 行，先读前 100 行和 `requestStrict`）**
为什么：前端所有和后端的接触面都在这一个文件。头部 100 行讲清了 `apiBaseUrl()` / `resolveApiUrl()` / `apiWebSocketBaseUrl()` 的区别（这是「Server Component 里 fetch 报 Failed to parse URL」这类 bug 的根因），`requestStrict`（约 1378 行）讲清了错误、401、402 的统一处理。之后再看具体页面组件会很轻松。

**第 7 步 — `packages/workers/scheduler.py` + `celery_app.py`**
为什么：产品里大量「用户没点任何按钮，数据却变了」的行为来自这里。注意 scheduler 的注释写明的 **SINGLE-ORCHESTRATOR INVARIANT**（`puregamma.dispatch_due_daily_briefs` 是唯一按用户分发路径，legacy 链路已下线但任务名仍注册为薄包装），以及它只 `send_task`、不执行重活的分工。

**第 8 步 — 第 5 节（部署真相）+ `deploy/release-build-chat-workspace.sh`**
为什么放在最后：此刻你已经知道代码长什么样，再读部署脚本才能把「这份代码怎么变成线上那个容器」串起来。重点掌握三件事：`/puregamma/.git-mirror` 导出确切 commit、`/puregamma/build-<sha>/` 是构建上下文、`docker inspect ... working_dir` 是唯一可靠的「线上是哪份代码」查询手段。

**如果只有两小时**：第 1 步 + 第 3 步 + `docker inspect` 那一条命令。这三样能覆盖你 80% 的「这代码到底在干嘛 / 改完去哪儿验证」的问题。

**English summary.** Read in this order: (1) `apps/api/main.py` — entry, middlewares, and the full URL map via `include_router`; (2) `apps/api/dependencies.py` + `packages/database/session.py` — session lifecycle, the hand-rolled HS256 JWT, and the fact that `init_db()` runs Alembic migrations; (3) one read path and one write path through `routers/portfolio.py` → `services/portfolio_service.py` → `packages/database/models.py`; (4) `models.py` by table name, plus the newest Alembic revisions; (5) `packages/agents/llm/base.py` + `provider_factory.py` — a *text completion* abstraction that silently degrades to `MockLLMProvider` when unconfigured (the first suspect for "the AI output is fake"); (6) `apps/web/lib/api.ts`, especially `apiBaseUrl()` vs `resolveApiUrl()` and `requestStrict`; (7) `packages/workers/scheduler.py` + `celery_app.py` for everything that happens without a button press; (8) the deployment truth from section 5 plus `deploy/release-build-chat-workspace.sh`. With only two hours, do steps 1 and 3 plus the `docker inspect` one-liner.

---

## 附录：本文档核对记录

| 项 | 核对方式 |
| --- | --- |
| 仓库分支 | `git branch --show-current` → `server/pm-live-20260916` |
| 目录与文件存在性 | 逐个 `ls` / `read`，行数来自 `wc -l` |
| 路由与端点 | 直接读 `apps/api/main.py`、`apps/api/routers/*.py` 源码 |
| CRLF/LF 统计 | `git ls-files --eol`（区分 index `i/` 与工作树 `w/`），`.gitattributes` 确认不存在 |
| 生产主机、SSH、`/puregamma/*` 布局、`.git` 指针内容、mirror 无本地提交 | 通过 SSH 在生产主机上实际执行 |
| 容器 → 目录映射 | 在生产主机上对所有运行中容器执行 `docker inspect ... com.docker.compose.project.working_dir` |
| `/puregamma/release-manifest.json` 与 override pin 已过期 | 对照同一时刻的 `docker ps` / `docker inspect` 实测结果 |

未核对但可自行确认的推断：`rsync → build-*` 两条路径各自最近一次使用时间（需要看 `~/.bash_history` 或发布记录，本次未做）。

**English summary.** Verification log: branch, directory/file existence, routers and endpoints, the CRLF/LF counts (from `git ls-files --eol`, with `.gitattributes` confirmed absent), the production host layout, the broken `.git` pointer and the commit-less mirror, and the container→directory mapping were all checked directly — the production items by executing commands over SSH on the host. The one inference not verified is when each of the two deployment paths was last used.

*核对日期：2026-09-18*
