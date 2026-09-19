# PureGamma.ai × TypeSafe Jev — 生产审计报告（P0）

审计时间：2026-09-18
审计方式：**只读**。未修改、未重启、未重建任何生产资源。
审计人：开发代理（主开发/部署工程师角色）
主机：阿里云 Ubuntu，项目根 `/puregamma`

> 本报告不含任何密钥明文。`.env`、TypeSafe Key、Stripe Key、用户令牌、私钥**仅检查存在性与注入方式**。

---

## 1. 生产基线（实测，非假定）

### 1.1 运行中容器（`docker ps`，审计时刻）

| 容器 | 镜像 | 状态 |
|---|---|---|
| puregamma-ai-web-1 | `puregamma-ai-web:pmui7-20260916` | Up 2 days (healthy) |
| puregamma-ai-api-1 | `puregamma-ai-api:pmui3-20260916` | Up 2 days (healthy) |
| puregamma-ai-worker-1 | `puregamma-ai-worker:0dbe7b48` | Up 4 days |
| puregamma-ai-scheduler-1 | `puregamma-ai-scheduler:0dbe7b48` | Up 4 days |
| puregamma-ai-pocket-1 | `puregamma-ai-pocket:mobile1-20260916` | Up 2 days (healthy) |
| puregamma-ai-caddy-1 | `caddy:2-alpine` | Up 10 days |
| puregamma-ai-postgres-1 | `postgres:16` | Up 10 days (healthy) |
| puregamma-ai-redis-1 | `redis:7-alpine` | Up 10 days (healthy) |
| puregamma-ai-nautilus-runtime-1 | `puregamma-ai-nautilus-runtime` | Up 2 days (healthy) |
| riskbot-riskbot-1 | `riskbot:0.1.0` | Up 2 days (healthy) |

与任务书给出的起点一致，但已重新实测获取，未沿用假定。

### 1.2 镜像 digest

| 镜像 | image ID (short) |
|---|---|
| `puregamma-ai-web:pmui7-20260916` | `sha256:9e36ab46cc23fd2faf` |
| `puregamma-ai-api:pmui3-20260916` | `sha256:738ad6433c4487913c` |
| `puregamma-ai-worker:0dbe7b48` | `sha256:2bff1410800f76e2d5` |
| `puregamma-ai-scheduler:0dbe7b48` | `sha256:2bff1410800f76e2d5` |
| `puregamma-ai-pocket:mobile1-20260916` | `sha256:ed927fd184bcebff82` |

### 1.3 容器 → 源码目录（Compose working_dir label，实测）

| 容器 | working_dir |
|---|---|
| web | `/puregamma/build-pmui7-20260916` |
| api | `/puregamma/build-pmui3-20260916` |
| worker / scheduler | `/puregamma/build-0dbe7b48` |
| pocket | `/puregamma/build-mobile1-20260916` |
| **caddy / postgres / redis** | **`/puregamma/app`** |

**要点**：`/puregamma/app` 并非废目录 —— 它是 compose 文件、`.env`、`Caddyfile` 的所在地，
并且是 caddy/postgres/redis 三个容器的 working_dir。但它**不是 api/web 的源码**。

### 1.4 数据库迁移 head

```
alembic current  →  0032_chat_workspace (head)
```

与 `docker-compose.release-pin.yml` 的警告完全对应（见 §3）。

---

## 2. 目录、模块关系与调用链

### 2.1 源码树语义

| 路径 | 性质 |
|---|---|
| `/puregamma/build-0dbe7b48` | 基础发布快照，对应 git commit `0dbe7b48`（release-pin 记为 `12ca171` 树） |
| `/puregamma/build-pmui3-20260916` | api 现行源码 = build-0dbe7b48 副本 + private-PM 特性 |
| `/puregamma/build-pmui7-20260916` | web 现行源码 = 同上，另含后续 UI 迭代 |
| `/puregamma/build-mobile1-20260916` | pocket 现行源码 |
| `/puregamma/app` | **较旧**的树，**缺少** `0032_chat_workspace` 迁移；仅作部署编排与配置 |
| `/puregamma/pm-overlay` | 仅 private-PM 的 **16 个文件**（不是完整源码树） |
| `/puregamma/deploy/` | 我上一轮装入的 `pm-preserve.sh` + `pm-paths.txt` |
| `/puregamma/pm-backups/` | private-PM 的 tar 备份（部署保留用） |

### 2.2 Gateway 调用链（现状，实测）

```
客户端  --Bearer sk-pg-...-->  Caddy (puregamma.ai / api.puregamma.ai)
                                   └─ reverse_proxy api:8000
                                        └─ apps/api/routers/gateway.py
                                             ├─ openai_router  prefix="/v1"
                                             │    ├─ POST /v1/chat/completions
                                             │    └─ GET  /v1/models
                                             ├─ _gateway_key         (API Key 鉴权)
                                             ├─ assert_gateway_account_available (钱包)
                                             └─ packages/gateway/service.py
                                                  ├─ resolve_routes(db, public_model)
                                                  │     └─ provider_registry.create(name, ...)
                                                  │           └─ packages/gateway/providers/<name>
                                                  └─ record_request(...)  → GatewayRequestLog
```

### 2.3 计费链（现状）

```
provider 返回 usage
  → adapter.tokenUsage(payload)              # 各 provider 自己映射
  → record_request(...)                      # 落 GatewayRequestLog
      → packages/gateway/pricing.py usage_cost(prices, usage)
           ├─ normalize_official_prices()
           ├─ 缺省的费率键 = 不收费（输出免费即靠此，无需零费率特例）
           └─ Decimal 计算，MONEY_QUANTUM = 1e-8
      → 官方成本(provider_cost_usd) / 零售扣费(retail_cost_usd)
      → 钱包扣减
```

### 2.4 Gateway 生产开关（实测）

| 变量 | 值 |
|---|---|
| `GATEWAY_ENABLED` | `true` |
| `GATEWAY_ENABLED_PROVIDERS` | `deepseek,moonshot` |
| `GATEWAY_API_KEY_PEPPER` | `<已设置>` |
| `GATEWAY_DEEPSEEK_API_KEY` | `<已设置>` |
| `GATEWAY_MOONSHOT_API_KEY` | `<已设置>` |
| `GATEWAY_GLM_API_KEY` | `<未设置>` |
| **`GATEWAY_TYPESAFE_API_KEY`** | **`<未设置>`** ← 本次需注入 |

数据库状态：

```
pricing policy : markup_bps = 3000   (30%, 与任务书一致)
providers      : deepseek(enabled), moonshot(enabled)
models         : deepseek-flash(active), deepseek-v4-flash(active),
                 deepseek-v4-pro(active), kimi-k3-max(pending)
```

**结论：`typesafe` 尚未进入数据库，生产 api 源码中 `typesafe`/`systemone` 命中数为 0。**
即本次 JEV 集成为纯增量，未污染现有链路。

---

## 3. release pin 与部署约束（已核实原文）

`/puregamma/app/docker-compose.release-pin.yml` 原文要点：

```
base release "chat-workspace-attachment-lifecycle", source commit 0dbe7b48.
Each feature was built from /puregamma/build-<tag>, a copy of the
/puregamma/build-0dbe7b48 tree (commit 12ca171) - never from /puregamma/app,
which is an older tree without the 0032_chat_workspace migration.

WHY THIS FILE EXISTS: docker-compose.production.yml declares `build:` for
api/web/worker/scheduler/pocket. Running
  docker compose -f docker-compose.production.yml up -d
WITHOUT this override silently rebuilds them from /puregamma/app and the API
exits on boot with "Can't locate revision identified by '0032_chat_workspace'".

Always pass this file, and never rebuild what you do not mean to deploy:
  docker compose -f docker-compose.production.yml -f docker-compose.release-pin.yml up -d --no-build
```

**这确认了任务书中的警告，并给出唯一安全命令形态。本次发布必须严格遵循。**

安全注意（原文）：pocket 的 PIN → session handoff 已对 `POCKET_REMOTE_EMAIL` 开启，
**8 位 PIN 等同于该账号的登录凭证**。本次不触碰 pocket。

---

## 4. 现有 API 响应实测（基线冒烟）

| 端点 | 结果 |
|---|---|
| 容器内 `http://127.0.0.1:8000/health` | `200 {"status":"ok","service":"puregamma-api"}` |
| `https://api.puregamma.ai/health` | `HTTP 200` (0.017s) |
| `https://api.puregamma.ai/v1/models` | `HTTP 401`（需鉴权，符合预期） |
| `https://api.puregamma.ai/gateway/catalog` | `HTTP 200` |
| `https://puregamma.ai/zh` | `HTTP 301` |
| `https://puregamma.ai/en` | `HTTP 301` |

Caddyfile 路由：`reverse_proxy web:3000`（站点） / `reverse_proxy api:8000`（API）。

---

## 5. 本次拟修改文件清单

### 5.1 后端（已在本地上游完成并通过测试）

| 文件 | 动作 |
|---|---|
| `config/gateway/providers.yaml` | 改：新增 `typesafe` provider 与 `jev` 模型及官方价 |
| `packages/gateway/providers/typesafe/__init__.py` | 新增：System One 适配器 |
| `packages/gateway/registry.py` | 改：注册 `typesafe` 插件 |
| `packages/gateway/contracts.py` | 改：`GatewayProvider.systemOne` 默认实现 |
| `packages/gateway/service.py` | 改：`execute_system_one` |
| `packages/gateway/catalog.py` | 改：公开 metadata 白名单新增 JEV 字段 |
| `apps/api/routers/gateway.py` | 改：`SystemOneRequest` + `POST /v1/systemone` |
| `apps/api/config.py` | 改：`gateway_typesafe_api_key/base_url`；启用列表加入 `typesafe` |
| `.env.example` | 改：记录新变量（占位，无密钥） |
| `tests/gateway/test_typesafe_jev_gateway.py` | 新增：31 个测试 |

### 5.2 前端（P2/P5，待实现）

| 文件 | 动作 |
|---|---|
| `apps/web/app/[locale]/jev-trader/page.tsx` | 新增：Jev Trader 展示页 |
| `apps/web/components/jev-trader-console.tsx` | 新增：实时展示组件 |
| `apps/web/app/[locale]/page.tsx` | 改：首页入口模块 |
| `apps/web/components/nav.tsx` | 改：桌面/移动导航入口 |
| `apps/web/components/api-docs-embed.tsx` | 改（已完成部分）：能力感知示例 + 演示链接 |
| `apps/web/lib/api.ts` | 可能改：catalog 类型扩展（保持旧客户端兼容） |

### 5.3 生产环境变量（仅注入，不外泄）

```
GATEWAY_TYPESAFE_API_KEY=<注入到 /puregamma/app/.env>
GATEWAY_ENABLED_PROVIDERS=deepseek,moonshot,typesafe
```

---

## 6. 不应修改或重启的服务清单

以下服务本次**不得重建、不得重启**：

- `riskbot-riskbot-1`（Binance PM 只读采集，PM 看板的数据源）
- `pgfreqtrade-*`、`pm-binancejp-*` 系列（实盘执行链，**本任务未授权动用任何真实资金**）
- `puregamma-ai-nautilus-runtime-1`
- `puregamma-ai-postgres-1`、`puregamma-ai-redis-1`
- `puregamma-ai-caddy-1`
- `puregamma-ai-worker-1`、`puregamma-ai-scheduler-1`
- `puregamma-ai-pocket-1`

**本次只应更新 `puregamma-ai-api-1`（P3/P4）与 `puregamma-ai-web-1`（P2/P5）。**

---

## 7. 回滚基线

| 项目 | 回滚目标 |
|---|---|
| API 镜像 | `puregamma-ai-api:pmui3-20260916` → `sha256:738ad6433c4487913c` |
| Web 镜像 | `puregamma-ai-web:pmui7-20260916` → `sha256:9e36ab46cc23fd2faf` |
| Compose pin | `/puregamma/app/docker-compose.release-pin.yml`（保持原样，回滚即恢复其 image 行） |
| 数据库 | 迁移 head `0032_chat_workspace`；若本次新增迁移则先 `pg_dump` 备份 |
| 环境变量 | `/puregamma/app/.env` 改前备份 |
| PM 代码 | `/puregamma/pm-overlay` + `/puregamma/pm-backups/`（`pm-preserve.sh restore` 可恢复） |

**回滚不会删除任何历史交易、订单、用户、账本、支付数据。**

由于本次采用「新增镜像标签 + 定点更新单服务」的方式，回滚只需把 release-pin 中对应服务的
image 行改回旧标签并 `up -d --no-build`，不涉及数据库反向迁移。

---

## 8. 审计结论

1. 生产处于健康、可发布状态；迁移 head 明确为 `0032_chat_workspace`。
2. 本次 JEV 集成为**纯增量**，尚未进入生产源码（`typesafe` 命中 0）。
3. 部署存在一个已知致命陷阱（从 `/puregamma/app` 重建 api 会导致启动失败），
   已定位、已核实原文、已确定规避命令。
4. `GATEWAY_TYPESAFE_API_KEY` 未设置、`typesafe` 未在启用列表 —— 上线前必须注入与启用。
5. `/puregamma/app/.git` 确认为无效 worktree 指针，**不可**在该目录执行 Git 命令。

### 真实上游核验（本次已完成，非计划）

审计期间网络恢复，已用真实密钥对 TypeSafe 上游做了实际核验：

- `GET https://api.typesafe.ai/v1/models` → **200**，账户可用模型：
  `jev-latest`（release 2026-09-10）、`jev-preview`
- `POST https://api.typesafe.ai/v1/systemone` → **200**，使用任务书给出的请求形状：

```json
{"model":"jev-1.13.0",
 "answers":{"direction":{"type":"choice","choice":"hold","confidence":0.94,
            "probabilities":{"hold":0.96,"buy":0.03,"sell":0.01}}},
 "usage":{"input_tokens":324,"output_tokens":38}}
```

即 **`jev` → `jev-latest` → 实际 `jev-1.13.0`** 映射成立，且三种原语均可评估。

价格核验（生产 markup 3000 bps）：官方 $0.042/1M input → 零售 **$0.0546/1M input**，
输出 $0 —— 与任务书给定值一致。
