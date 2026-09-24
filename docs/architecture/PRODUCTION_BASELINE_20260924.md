# PureGamma 生产基线（2026-09-24）

本文件是 2026-09-24 的只读调查结果，作为本轮 Agent/Skill/NAV 改造的**事实基准**。
它记录"服务器 / 本地 / GitHub"三方的真实差异，不包含密钥、完整用户数据或真实财务明细。

调查方法：`ssh` 只读命令、`rsync -rcn`（内容校验、dry-run）双向比对、`git ls-remote` / `git rev-parse`
逐文件 blob 比对、生产容器与数据库只读查询。所有结论都可复现。

---

## 1. 生产服务器（事实基准）

| 项 | 值 |
| --- | --- |
| 主机 | `47.245.55.228`（root，密钥在本机，不入库） |
| 部署方式 | Docker Compose：`/puregamma/app/docker-compose.production.yml` + `docker-compose.release-pin.yml`，env 为 `/puregamma/app/.env` |
| 运行镜像 | `puregamma-ai-api:harness-20260921b`（healthy）、`puregamma-ai-web:harness-20260921b`（healthy） |
| Web 启动 | `node server.js`（Next.js standalone，非 DSH Web） |
| API 启动 | `python -m scripts.db_migrate upgrade && exec uvicorn apps.api.main:app` |
| 构建源树 | `/puregamma/build-harness-20260921`（2026-09-21 10:58 解包，**不是 git 仓库**） |
| 数据库 | `alembic current` = `0032_chat_workspace`；迁移文件 34 个 |
| 数据基线 | `users=21, trading_accounts=1, gateway_api_keys=11, gateway_request_logs=8` |
| 边缘 | Caddy：`app.puregamma.ai` → `web:3000`；`/api` → `api:8000` |
| 未动服务 | postgres / redis / caddy / worker / scheduler / pocket / nautilus-runtime，以及非 PureGamma 的 riskbot / freqtrade / pm-loop / 3x-ui |

### 1.1 部署源树 == 哪个 commit

用 17 个与本地不同的文件做 blob 比对，得分最高的候选是 **`ff3b0d0`（16/17）**
（`origin/integration/harness-main`，2026-09-20 17:46 `fix(harness): map main mobile access and live-trading routes to separate plugins`）。

唯一的第 17 个文件是 `apps/api/config.py`，差异是**服务器上手工热补丁**：

```
+ gateway_typesafe_api_key / gateway_typesafe_base_url
+ jev_advisory_enabled / jev_advisory_telemetry_path
+ pm_riskbot_export_dir / pm_account_allowed_emails / pm_account_label
~ GATEWAY_ENABLED_PROVIDERS 默认值加入 typesafe
```

该补丁**内容已被本地 `puregamma-ai-harness-core-v2/apps/api/config.py` 完全包含**（逐 key 核对），
所以服务器上没有"只存在于服务器"的有效源码改动；但它是**未提交**的，GitHub 上没有。

> 说明：`/puregamma/build-harness-20260921/.deployed-commit` = `12ca171`，
> `/puregamma/app/.git` 是指向 Mac 路径的失效 worktree 指针。两者都**不能**作为版本依据。

### 1.2 结论

**服务器源码树 ⊂ `puregamma-ai-harness-core-v2` 工作区**：`rsync -rc` 比对 13,000+ 文件，
`>f+++++++++`（仅服务器存在）计数 = **0**；内容不同的文件 **17 个**，且全部是本地/分支更新。

---

## 2. 本地两个工作区

工作目录 `/Users/christse/Desktop/puregamma.ai` 下有**两个** PureGamma 检出，历史不同源：

| | A：`puregamma-ai-harness-core-v2` | B：`puregamma-ai` |
| --- | --- | --- |
| 分支 | `cutover/harness-full`（= `origin/cutover/harness-full`） | `server/pm-live-20260916` |
| HEAD | `928be29`（2026-09-21 14:53） | `33c852e`（2026-09-19 11:16） |
| 工作区 | **13 改 + 11 未跟踪**（见 §2.1） | 干净 |
| 未推送提交 | 0（分支已推送；新工作未提交） | **15 个（GitHub 上完全没有）** |
| 与服务器差异 | 0 个仅服务器文件；17 个文件内容更新 | 0 个仅服务器文件；241 个文件内容不同 |
| DSH/Cordis 工作 | 有（`harness/` profile + 60+ 插件） | 无 |

两个检出都**包含**服务器源码树；A 与服务器只差 17 个文件，B 差 241 个文件（分叉实现）。

### 2.1 A 工作区未提交内容（本轮要收尾的"大改"）

```
M .gitignore                                   ?? harness/plugins/chat-workspace/
M harness/package.json                         ?? harness/plugins/mobile-access/
M harness/packages/client-gateway/package.json ?? harness/plugins/pm-nav/
M harness/packages/client-gateway/src/index.ts ?? harness/plugins/ui-pm-nav/
M harness/packages/client-gateway/src/types.ts ?? harness/plugins/wallet-auth/
M harness/plugins/catalog.ts                   ?? harness/profile/cordis.yml
M harness/plugins/contracts.ts                 ?? harness/scripts/{pm-nav,mobile-access,wallet-auth,chat-workspace}.test.mjs
M harness/plugins/legacy-surface-map.ts
M harness/plugins/legacy-web-surface-map.ts
M harness/profile/cordis.patch.yml
M harness/profile/package.json
M harness/scripts/release-boundary.test.mjs
M harness/tsconfig.json
```

13 个已跟踪文件合计 +279/-7 行；5 个新插件包（`pm-nav`、`ui-pm-nav`、`mobile-access`、
`wallet-auth`、`chat-workspace`）+ 4 个测试脚本 + 1 个 profile 根组合文件。
`harness/pm-nav-check` 本地 15/15 通过。

### 2.2 B 中不在 GitHub、也不在 A 的内容

- 3 个文件只在 B 存在：`apps/api/routers/jev_trader.py`、`apps/api/services/jev_trader_service.py`、
  `apps/web/components/jev-trader-console.tsx`（Jev Trader 后端 + 控制台）。
- B 的 15 个未推送提交（Jev Trader 摄取/只读 API/仪表盘、私密 PM 部署保活脚本、JEV 决策包、审计文档）。
- **注意**：生产 `/zh/jev-trader` 页面渲染的是 `JevAdvisoryConsole`（advisory 口径，来自主线），
  与 B 的 `JevTraderConsole` 是**同一路由上的两套不同实现**。B 的实现**未部署**。

→ 处理策略：B 作为**历史保全分支**推送到 GitHub（不合并、不覆盖主线），
其独特价值（Jev Trader）由用户决定是否并入；主线以 A 为准。

---

## 3. GitHub（`xxxxxwater/puregamma-ai`）

| ref | commit | 说明 |
| --- | --- | --- |
| `origin/main` | `0260979`（2026-09-21 15:41） | 已含 Cordis refactor 集成 + JEV + main-only 路由所有权台账 |
| `origin/cutover/harness-full` | `928be29` | 本轮工作分支 |
| `origin/integration/harness-full-20260921` | `9c5f2a39` | |
| `origin/integration/harness-main` | `ff3b0d0` | **= 服务器源码基线** |
| `origin/refactor/harness-core-v2` | `dc68fcc` | |
| 其他 | `design/*`、`feature/*`、`release/2.2-predeploy` 等 | |

**逐路径核查结果**：

- `harness/plugins/{pm-nav,ui-pm-nav,chat-workspace,mobile-access,wallet-auth}` 在**任何远端分支上都不存在**。
- B 的 15 个提交在**任何远端分支上都不存在**。
- `origin/main` 相对服务器：多了 Cordis refactor 集成与 JEV；`apps/api/config.py`、`apps/api/services/agent_service.py`、
  `packages/agents/chat/tools.py`、`harness/plugins/pg-tsy-runtime-http/src/index.ts` 等已比服务器新。

---

## 4. Agent 对话现有真实链路（改造对象）

```
浏览器 apps/web/app/[locale]/chat
  → components/agent-chat.tsx（596 行）
      · 会话列表/重命名/删除、模型选择、数据源开关、**Skill 多选**、自定义提示、附件
      · POST /agent/conversations/{id}/messages → SSE
  → apps/api/routers/agent.py
  → apps/api/services/agent_service.py（1155 行）
      · _prepare_agent_context：Skill 解析 + 工具白名单 + 数据源裁剪
      · packages/skills/registry.py（SkillRegistry）
      · packages/agents/chat/tools.py（确定性工具计划）
  → apps/api/services/agent_answer_service.py（SSE：run.started / plan.ready /
      tool.started / tool.completed / evidence.ready / citation / message.delta /
      message.completed / run.failed / run.canceled）
```

持久化：`conversations` / `agent_messages` / `agent_runs` / **`agent_tool_calls`**（已存在）/ 附件。
自研 Skill 资产：表 `skills`、`skill_versions`、`skill_installations`、`skill_runs`、`skill_permissions`、
`skill_sources`（迁移 `0011_skills_library`）+ `packages/skills/*` + `/api/skills*`。
**除 Agent 对话外的消费者**：`routers/backtest.py`、`routers/reports.py`、`routers/strategies.py`、
`services/skill_workflow_service.py` —— 这些按用户要求保留。

## 5. NAV PM 私有化现有真实链路

```
Binance PM（只读 API Key 只在 riskbot 手里）
  → riskbot 容器（/opt/riskbot，独立服务，非本仓库）
      · /data/riskbot.db: account_snapshot / position_event …
      · 每 ~15s 落一条快照；导出 /srv/riskbot-export/{latest.json,series.json}（原子替换）
  → 挂载 ${PM_RISKBOT_EXPORT_DIR}:/var/lib/puregamma/riskbot:ro（api 容器）
  → apps/api/services/pm_riskbot_service.py（PmAccountReader，283 行）
  → apps/api/dependencies.py require_pm_account_viewer（白名单来自 PM_ACCOUNT_ALLOWED_EMAILS，空=拒绝所有人）
  → GET /portfolio/pm、GET /portfolio/pm/history
  → apps/web/components/pm-account-panel.tsx（554 行，挂载于 portfolio-console.tsx）
```

- 三个授权邮箱：`PM_ACCOUNT_ALLOWED_EMAILS`（compose 环境变量，3 个地址，报告中脱敏）。
- 只读性：PureGamma 不持有交易所凭证，`merged_into_portfolio_nav=false`，无下单能力。
- 数据新鲜度字段：`snapshot.captured_at`、`is_stale`、`stale_after_seconds`；服务端 `STALE_AFTER_SECONDS=180`。

---

## 6. 差异摘要（一句话版）

1. **服务器**运行 `ff3b0d0` 源码树 + 一处未提交的 `config.py` 热补丁；补丁内容已在本地。
2. **本地 A** 是服务器的严格超集，并携带未提交的 Cordis/DSH 插件化大改（5 个新插件）。
3. **本地 B** 是另一条分叉线，含 15 个从未推送的提交（Jev Trader 等），必须保全。
4. **GitHub** `main` 已含集成后的 refactor，但**没有**这 5 个新插件，也**没有** B 的提交。
5. 服务器没有任何"只存在于服务器"的文件；因此不存在"用本地旧代码覆盖服务器"的风险，
   反过来需要避免的是**丢掉本地未提交/未推送的工作**。
