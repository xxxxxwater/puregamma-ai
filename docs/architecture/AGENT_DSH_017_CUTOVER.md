# Agent / Skill / NAV 改造设计（基准：DSH `dsh-v0.1.7-rc.1`）

- 上游：https://github.com/deepseek-ai/deepseek-harness/
- 固定 tag：**`dsh-v0.1.7-rc.1`** → commit **`46a7f68b0922371ce7144b668b90e377d8e799f4`**（本文件所有上游引用均指该 commit）
- 现状基准：`docs/architecture/PRODUCTION_BASELINE_20260924.md`
- 许可：上游仓库与全部 307 个 `packages/*/*` 均为 **MIT**（`LICENSE`, `Copyright (c) 2026 DeepSeek`）。
  MIT 只要求保留版权与许可声明，商业闭源产品可直接依赖；本项目已有 `THIRD_PARTY_NOTICES.md`，需补记 DSH 条目。
  需单独注意的非宽松依赖（**本轮不引入**）：`@deepseek-ai/libreoffice-kit`(MPL-2.0)、
  `@anthropic-ai/claude-agent-sdk`(自定义条款)、`lightningcss`(MPL-2.0，构建期)。

---

## 0. 结论摘要

| 目标 | 结论 |
| --- | --- |
| Agent 对话采用 DSH 的 UI/会话端设计 | **采用"设计对齐 + 产品内实现"**：会话端语义按 DSH 事件日志/投影/按 seq 续传实现，UI 按 DSH Web 交互在 PG 现有前端实现 |
| 是否直接把 DSH Web 作为线上对话入口 | **不采用**（证据见 §1.3）。上游明确是单操作者 localhost 工具，无用户/租户模型 |
| 自研 Skill 机制 | **退出 Agent 对话路径**，改用 DSH 默认 Skill 设计（磁盘 `SKILL.md` + 会话目录 + `skill` 工具 + `/name`）；其它消费者（回测/报告/策略）保留 |
| 上游版本 | `vendor/deepseek-harness` 从 `0.1.5-rc.2`(`c291e79`) 升到 **`dsh-v0.1.7-rc.1`**(`46a7f68`) |
| NAV PM 金额 | **两个根因**：导出查询取到窗口内最旧 5000 条（曲线冻结在 7 天前）＋ Y 轴刻度固定 2 位小数导致分辨率丢失 |

---

## 1. Agent 改造架构

### 1.1 PG 现有 Agent 与 DSH 固定版本的组件对照

| 能力 | PureGamma 现状 | DSH `dsh-v0.1.7-rc.1` | 本轮选择 |
| --- | --- | --- | --- |
| 会话持久化 | Postgres `conversations`/`agent_messages`/`agent_runs` | `@deepseek-ai/dsh-session-persistence-jsonl`，`$DSH_HOME/sessions/**/session.vN.jsonl` | **产品内实现**（Postgres），语义对齐 |
| 会话事件 | 无事件日志；只有消息行 + SSE 瞬时帧 | append-only、带 `seq` 的 `SessionEvent`（`turn/start`、`step/start`、`tool/call`、`tool/result`、`assistant/message`、`turn/end`…） | **产品内实现**：新增 `agent_run_events` 表，事件名/语义对齐 |
| 断线续传 | 无（刷新即丢当前流） | `follow` 传"已持有的最后 seq"，返回无缺口帧 | **产品内实现**：`GET /agent/runs/{id}/events?after=seq` |
| 中断 | `POST /agent/runs/{id}/cancel` | `cancel` 只取消当前 turn，**不清空待处理 inbox** | **适配**：取消后保留用户消息与队列 |
| 压缩 | 无 | `compaction/{start,summary,end,prune}` 事件 + `basic`/`command-compact` | **本轮不实现**（记为后续），保留现有 summary 字段 |
| 工具过程 | `agent_tool_calls` 表已存在，UI 未按行呈现 | `tool/call`+`tool/result` 事件 + keyed `tool.call.toolview` 行组件 | **产品内实现**：持久化 + 工具行 UI |
| Skill | `packages/skills` 注册表（DB 版） | `ctx.skills` 注册表 + `SKILL.md` 目录发现 + `skill` 工具 + `/name` + `ui-skill` | **采用 DSH 设计**，见 §2 |
| UI 外壳 | Next.js `apps/web`（品牌/导航/鉴权/计费齐全） | `@deepseek-ai/dsh-web-app`（`dsh --profile web`，仅品牌+对话+组合；**无鉴权**） | **产品内实现**：UI 交互对齐，保留 PG 外壳 |
| 前端插件 | React 组件 | `window.__ModuleLoader__` 闭包工厂 + slot 体系，外部表仅 react/cordis/ui-slots 等 | **不直接复用**（复用等于把 DSH Web 变成入口） |

### 1.2 为什么不是"直接集成 DSH Web"

上游事实（均可复核）：

1. **没有多用户/租户模型。** `BrowserAuth` 每个 Harness home 只有**一个**签名密钥；`?token=` 换取的 cookie
   "not scoped to a user, session, workspace, or role"，持 cookie 即全操作者权限。
   `/api` 的 trust fence 自述 "this fence is not an auth layer"。
2. **不允许对外监听。** `--host 0.0.0.0` 是硬错误，报错原文：
   "it would expose remote code execution to the network; use 127.0.0.1 instead"。
3. **沙箱是同内核约束，不是容器。** `sandbox-local` 共享宿主内核/文件系统，Windows 与旧 Landlock 上
   自报 `partial`；`SAFETY.md` 明确 "must not be treated as secure or production-ready"。
4. **默认 web profile 仍带高危能力**：bash/pwsh、工作区写、出网、PTC（模型自写代码执行）、subagent、
   会话日志落宿主磁盘。
5. **仓库自身的迁移门禁**（`docs/architecture/HARNESS_CORE_V2.md`）把"以 Harness profile 作为生产入口"
   放在 **Slice 5 的最后一步**，前置是逐能力的 parity gate。

→ 结论：把 DSH Web 直接暴露给线上付费用户会破坏 PG 的身份/租户/计费/安全模型。
采用 **适配层 + 产品内实现**，并把 DSH 的**语义契约**（Skill 格式、会话事件、续传、工具行）作为基准。

### 1.3 部署拓扑（本轮）

```
Caddy(app.puregamma.ai)
 ├── /api/*            → api:8000      （FastAPI，PG 鉴权/租户/计费/SSE；会话事件由 PG 拥有）
 └── /*                → web:3000      （Next.js；/chat 采用 DSH 交互设计）
        api ⇄ postgres（conversations / agent_messages / agent_runs / agent_tool_calls /
                        agent_run_events / skill_runs…）
        api  ←只读挂载→ /srv/riskbot-export（PM NAV）
riskbot（独立容器，/opt/riskbot）：Binance PM 只读采集 → 导出 bundle
```

`vendor/deepseek-harness`（`dsh-v0.1.7-rc.1`）与 `harness/` 插件树**随仓库构建**，作为
可追溯的运行时/插件契约基准；**不新增对外监听端口**，不托管线上会话。

### 1.4 数据所有权与故障边界

- **会话数据归 PG**（Postgres），DSH 事件模型只是语义来源；DSH 版本升级不影响用户数据。
- **Skill 归 PG**（服务端按用户解析），磁盘 `SKILL.md` 是官方技能的载体。
- **故障边界**：Agent 运行失败不影响其它页面；事件流断开可由 `after=seq` 重放恢复；
  NAV PM 数据源（riskbot）失联时 API 返回 `available:false` 而不是伪造数字。

---

## 2. Skill 迁移（自研 → DSH 默认设计）

### 2.1 现有自研 Skill 的全部入口/数据/消费者

| 资产 | 位置 | 本轮处置 |
| --- | --- | --- |
| 注册表 | `packages/skills/{registry,manifest,builtins,policy,workflows}.py` | **保留**（其它消费者仍用） |
| 数据表 | `skills`/`skill_versions`/`skill_installations`/`skill_runs`/`skill_permissions`/`skill_sources`（迁移 `0011`） | **保留，不删不改** |
| HTTP | `/api/skills*`（`routers/skills.py`） | **保留** |
| 服务 | `services/skill_service.py`、`services/skill_workflow_service.py` | **保留** |
| Agent 对话内 | `services/agent_service.py`（16 处）、`routers/agent.py`（8 处）、`agent-chat.tsx` Skill 多选 | **移除**，改用 §2.2 |
| 其它消费者 | `routers/backtest.py`、`routers/reports.py`、`routers/strategies.py` | **不动** |
| 审计 | `skill_runs` | **继续写**（同一张表，新增 `mechanism` 区分 `registry` / `dsh-skill`） |

### 2.2 新旧对应关系

DSH 默认设计的四件事（严格照做，格式逐字节对齐上游）：

1. **发现**：磁盘根扫描，目录包 `<root>/<name>/SKILL.md` 或平铺 `<root>/<name>.md`，**最大深度 2**。
2. **格式**：YAML frontmatter 必须含 `name`（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）与 `description`；
   可选 `whenToUse`、`metadata`、`disable-model-invocation`、`user-invocable`。
   布尔接受 `true/false`、`1/0`、`yes/no`、`on/off`；非法值**丢弃该技能**并告警（不静默放行）。
3. **模型侧**：会话目录以 `<system-reminder><available_skills>` + `` - `name`: description `` 注入；
   `skill` 工具入参只有 `name`；正文用
   `<skill_content name="…"><skill_resources>…</skill_resources>\n\n<skill_instructions>…</skill_instructions></skill_content>` 包裹。
4. **用户侧**：`/(^|\s)\/([a-z0-9]+(?:-[a-z0-9]+)*)(?=\s|$)/`，**只扫描用户发来的文本**
   （外部内容不能伪造该手势），命中后追加一条 skill-invocation 消息；未知或 `user-invocable: false` 的保持普通文本。

| 旧（自研） | 新（DSH 默认设计） |
| --- | --- |
| `skills`/`skill_versions` 行 + `registry.resolve_chat_contract()` | 磁盘 `SKILL.md` 目录包 + 服务端目录解析 |
| 请求体 `skills` / `skill_refs` 显式选择 | **会话目录自动注入 + `skill` 工具按名加载**；请求体不再携带技能选择 |
| `skill_installations`（按用户启用） | PG 服务端按用户/租户**过滤目录**（多租户边界仍在 PG） |
| `validate_chat_contract` + 工具白名单裁剪 | 技能正文声明 + PG 既有工具权限层（**不放松**任何权限） |
| UI：Skill 多选下拉 | UI：`/` 斜杠菜单 + Instructions 工具行 |
| 6 个内置 slug（`market_research` 等） | 转写为 6 个 `SKILL.md`（同名同义），能力不减少 |

### 2.3 迁移步骤（可重复执行、可识别已迁移）

1. 新增 `apps/api/services/agent_skills.py`：DSH 规范的加载器 + 目录渲染 + `/name` 解析（纯函数，可测）。
2. 官方技能落盘到 `apps/api/skills/`（随镜像发布，只读）。**已迁移判定**：目录存在且 frontmatter 合法即跳过。
3. `agent_service._prepare_agent_context`：删除注册表解析；注入会话目录；注册 `skill` 工具；
   解析用户文本里的 `/name`。
4. `agent-chat.tsx`：删除技能多选；新增 `/` 菜单与技能工具行。
5. `skill_runs` 继续写入（`mechanism='dsh-skill'`，`skill_id` 用旧 slug 的映射保持可对账）。
6. 旧接口/旧页面**不删**，仅在对话入口下线；`/api/skills` 仍可用。

### 2.4 无法直接对应的行为（如实记录）

- 自研的 **schema 校验 / 成本上限 / 速率限制 / 安装粒度** 由 `SkillRegistry` 在调用前强制；
  DSH 设计里这些不在 Skill 层，而在**工具权限与计费层**。本轮把成本/速率约束保留在
  PG 既有的 quote→reserve→settle 链路（不放松），把 schema 校验降级为"技能作者责任 + 目录说明"。
- `disable-model-invocation` 语义照上游实现（只允许用户 `/name` 调用）。

---

## 3. 会话模型

### 3.1 与 DSH 的对应

| DSH | 本轮 PG 实现 |
| --- | --- |
| `SessionEvent{type,seq,time,data}` append-only | 新表 `agent_run_events(id, run_id, seq, type, data JSONB, created_at)`，唯一键 `(run_id, seq)` |
| `turn/start` / `turn/end` / `step/start` / `step/end` | 同名事件 |
| `tool/call` / `tool/result` | 同名事件（并写既有 `agent_tool_calls` 供审计） |
| `assistant/message` + 流式 delta | 保留 `message.delta`，最终落 `assistant/message` |
| `user/message` `source.kind='skill-catalog'` | 会话目录注入作为事件（可重放、可审计） |
| `user/message` `source.kind='skill-invocation'` | `/name` 命中的注入事件 |
| `follow`（传最后 seq，无缺口） | `GET /agent/runs/{id}/events?after=<seq>`（SSE，先重放后跟随） |
| `cancel`：取消 turn，保留 inbox | `POST /agent/runs/{id}/cancel` 后用户消息与队列保留，事件写 `run.canceled` |

### 3.2 流程

- **新建**：`POST /agent/conversations` → 会话行（`user_id` 绑定）。
- **发送**：`POST /agent/conversations/{id}/messages` → 建 run（`seq` 从 1）→ SSE 首帧为
  `snapshot{run_id, last_seq, messages, projections}`，之后逐事件推送。
- **流式**：每个 SSE 帧带 `seq`；客户端记录 `last_seq`。
- **中断**：`cancel` 只终止当前 turn；已入队消息不丢。
- **重连**：断线后 `GET /agent/runs/{id}/events?after=last_seq`，先重放缺口再转跟随。
- **刷新恢复**：`GET /agent/conversations/{id}/messages` + 若存在未完成 run，则按 3.2 重连。
- **历史/归档**：会话列表 + 归档（`archived_at`），不物理删除用户历史。
- **附件**：沿用 `chat_workspace` 的租户隔离存储与鉴权下载。
- **工具结果**：`tool/call`（含 `args` 摘要）→ `tool/result`（含状态与输出摘要），UI 折叠行。

### 3.3 隔离（硬约束）

- 所有查询强制 `user_id` 过滤（沿用现状）；事件表读写按 `run_id → conversation.user_id` 校验。
- 事件流、恢复接口、附件地址三类入口都做归属校验；跨用户一律 404/403，不泄露存在性。
- 技能目录按用户解析，**不得**把 A 用户的技能/历史出现在 B 用户目录里。

---

## 4. UI 设计（对照 DSH Web 实际界面）

| DSH Web 元素 | 本轮 | 说明 |
| --- | --- | --- |
| 会话列表 / 新建 / 归档 | **实现** | PG 已有列表；补归档与"继续会话" |
| 会话标题自动生成 | **适配** | 沿用现有人工重命名；`session/title` 语义后续 |
| 消息流（markdown、代码块、引用） | **实现** | 已有 `ReportMarkdown` |
| 流式 delta | **实现** | 已有 `message.delta`，补 `seq` 与续传 |
| **工具过程行（可折叠、replay-stable）** | **实现** | 按 `tool/call`+`tool/result` 渲染；技能行显示技能名 + Instructions 卡 |
| `/` 斜杠技能菜单 | **实现** | DSH `ui-skill` 的 `trigger:'/'`、按名排序；`onPick` 只写入 `/name ` 纯文本 |
| 输入区（附件、模型、模式） | **适配** | 保留 PG 的模型选择/研究模式；**移除 Skill 多选** |
| 中断 / 停止 | **实现** | 取消当前 turn，保留已输入内容 |
| 重连 / 恢复状态 | **实现** | 断线横幅 + 自动按 `after=seq` 重放 |
| 空状态 / 加载状态 / 错误 | **实现** | 已有；补"运行中断开"与"事件缺口"两种明确状态 |
| 附件预览 | **适配** | 已有附件卡；补预览与下载鉴权 |
| 响应式布局 | **适配** | 保留 PG 断点 |
| 右侧栏（文件预览、SKILL.md 打开） | **不适用** | PG 对话不暴露工作区文件；技能以卡片呈现正文 |
| 终端 / 文件树 / 插件管理 / 设置面板 | **不适用** | 单机开发者能力，按 §1.3 不向线上用户开放 |
| 会话 fork / 子代理 / todo 面板 | **不适用（本轮）** | 记为后续，不展示假入口 |
| 品牌与导航 | **保留 PG** | `@puregamma/dsh-ui-brand` 与 PG 导航不变 |

---

## 5. 权限与用量

- 鉴权：全部沿用 `get_current_user`（cookie/Bearer）；无匿名路径。
- 权限：`require_pm_account_viewer` 等现有依赖不变；本轮**不新增任何模型工具权限**，
  技能正文不能提权（`skill` 工具只返回文本，不触发工具）。
- 用量与计费：沿用 `POST /agent/quote` → 预留 → 结算；技能调用仍写 `skill_runs`/用量行。
  兼容性处理：旧记录字段不变，新增 `mechanism` 列区分来源；旧行不回填、不迁移。
- 失败/取消：失败不记成功用量（沿用现状），事件里保留 `run.failed` 原因。

---

## 6. NAV PM 修复方案

### 6.1 预期口径（从代码与数据确认）

- 主数字 = `account.adjusted_equity_usd`（官方 actualEquity，市值−负债）。
- 曲线 = `series.points[].adjusted_equity_usd`，**同一字段**；仅真实快照，不插值、不伪造。
- 三邮箱：`PM_ACCOUNT_ALLOWED_EMAILS` 的 3 个地址看到**同一份** bundle；未列入者 `available:false`/403，
  且**不触发读取**。

### 6.2 错误示例与根因（已从运行环境证实）

**根因 A（数据来源/查询）。** riskbot `repositories.series()`：

```sql
SELECT … FROM account_snapshot WHERE captured_at >= ? ORDER BY captured_at ASC LIMIT 5000
```

`since = generated_at - export_history_days*86400`（90 天）。90 天窗口内的真实行数远超 5000，
`ORDER BY ASC` 取到的是**窗口内最旧的 5000 条**，因此 `series.json` 永久冻结在采集最初的约 21 小时。

实测（2026-09-24 只读查询）：

```
account_snapshot: 23,248 行，跨度 09-16 10:54Z → 当日
第 5000 行（ASC）= 09-17 08:25:38Z
series.json: 首点 09-16 10:59:55Z，末点 09-17 08:25:38Z  ← 与"第 5000 行"完全一致
latest.json: 正常更新（当日）
```

→ 页面上"主数字是当日、曲线与纵轴却是约 7 天前"的口径差，正是用户看到的"金额不对"。

**根因 B（前端格式化）。** `compactUsd()` 在百万量级固定 `toFixed(2)`；当 Y 轴 `domain` 收窄到几万美元时，
相邻刻度会被格式化成**相同或不可分辨**的标签，纵轴读不出真实金额。

### 6.3 修复

1. **riskbot 导出查询**改为"覆盖整个窗口的分层抽样，只取真实观测"：
   近 24h 每 5 分钟、1–7 天每 30 分钟、更早每 2 小时，各取该桶内**最后一条真实行**（不插值）。
   参数化桶宽，行数上限固定，窗口越界自动分页/落桶，避免再次退化为"最旧 N 条"。
2. **API** `nav_history_view()` 增加 `latest_point_at` / `data_as_of` / `stale` / `stale_after_seconds`
   （由服务端时钟判定），曲线陈旧时前端必须显式提示。
3. **前端** Y 轴刻度按实际跨度自适应小数位（保证相邻刻度可分辨）；曲线区显示真实时间范围；
   陈旧时打出警告条，绝不把 7 天前的曲线当作"当前净值"。

### 6.4 不做的事

- 不写入、不修改任何真实财务记录；不"重算"历史。
- 不为缺失快照插值或补点。
- 三个邮箱的可见性不变。

---

## 7. 数据迁移与回滚

| 项 | 方案 |
| --- | --- |
| 迁移 | 只增不改：`0033_agent_run_events`（含 `mechanism` 列的 `skill_runs` 增量在 `0034`，如需要）。历史迁移一律不动 |
| 向前兼容 | 旧代码不读新表；新代码对缺失/空表降级为"无事件"，不报错 |
| 备份 | `pg_dump`（custom，no-owner）+ `.env` + `docker-compose.release-pin.yml` + riskbot `export.py` |
| 应用回滚 | `release-pin` 指回 `puregamma-ai-api:harness-20260921b` / `-web:harness-20260921b`，`up -d --no-build --no-deps api web` |
| 数据回滚 | 新表保留不删（回滚不丢新会话）；如需彻底回退，用备份库在新目录恢复，**不清空生产库** |
| riskbot 回滚 | 恢复 `export.py` 备份 + `docker compose -f /opt/riskbot/docker-compose.yml up -d --build riskbot` |
| 已产生的新会话数据 | 回滚后仍可读（旧代码忽略事件行），不删除 |

---

## 8. 验收标准

**Agent（必须真实可测）**

1. 新建会话 → 发送 → 收到带 `seq` 的流式响应 → 事件落库（`turn/start`…`turn/end`）。
2. 刷新页面/重开浏览器 → 会话历史完整；未完成 run 能从 `after=last_seq` 无缺口续上。
3. 断网 → 界面对"连接中断"给出明确状态；恢复后补全缺口，**不丢消息**。
4. 中断：点击停止 → `run.canceled`，用户消息仍在，可直接再发。
5. 工具行：出现可折叠的工具过程行；技能加载呈现为技能行 + Instructions 卡。
6. `/name`：`/market-research …` 命中并注入；未知名字保持纯文本。
7. 隔离：用户 B 用 A 的 conversation_id / run_id / 附件 id 一律被拒，事件流不泄露内容。

**NAV PM**

8. 三个邮箱各自可见同一份只读数据；未列入的邮箱看不到面板且不产生读取。
9. 曲线末点时间 = 最近真实快照（分钟级），纵轴金额与主数字口径一致、刻度可分辨。
10. 页面无任何写财务数据的入口或请求（只读断言）。

**回归**

11. `/zh`、`/en`、`/portfolio`、`/mobile-access`、`/trading/live/*`、`/zh/jev-trader` 正常。
12. 鉴权、用户数据、`gateway_api_keys`/`gateway_request_logs` 计数与基线一致（只增不减）。
13. `alembic current` 为目标版本；容器 healthy；日志无新增异常。

---

## 9. 本轮交付切片（如实标注）

已实施并验证的切片、以及**未实施**的部分（不得当作已上线能力），在最终交付报告中逐条列出；
未实施项保留经典实现，不做"先删后建"。
