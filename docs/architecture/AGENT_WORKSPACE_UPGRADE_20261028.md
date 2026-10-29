# Agent 工作区升级（2026-10-28）

状态：代码与测试已完成，**未执行任何生产部署、生产数据库迁移、切流或实盘开启**。
分支：`upgrade/agent-workspace-20261028`，基于 `main@eae35c4`。

本文件依次记录：事实基线、现状矩阵、架构取舍、迁移表、功能对照、视觉核查、测试证据、未上线事项、Codex 评估和回滚办法。

---

## 1. 事实基线（开发时实测）

| 项 | 实测值 |
| --- | --- |
| `main` HEAD | `eae35c4`（2026-10-28 07:59 UTC），两个商业 CI gate 均为绿色 |
| 默认分支 `refactor/harness-core-v2` | `34ae868`，落后 `main` 130 个提交，领先 0 个；只是历史参考，**不是**最新代码 |
| `vendor/deepseek-harness` gitlink | `46a7f68` = tag `dsh-v0.1.7-rc.1`（CI 校验） |
| `vendor/pg-tsy-core-bootstrap` gitlink | `f5a6382` |
| `harness/README.md` 记载的 pin | 当时写的是 `c291e79` / `d7e719b`，**与 gitlink 不符**。本次已修正，并加了 CI 守卫 |
| Harness 编译依赖 | `harness/package.json` 用的是 npm 上的 `@deepseek-ai/*@0.1.5-rc.2`，**不是** vendored 的 0.1.7-rc.1 源码（见 §7） |
| `AGENTS.md` | 仓库中不存在 |
| 预览站 `new.puregamma.ai` | 可以访问。公开页面已截图（桌面/手机 × 浅色/深色）；`/chat` 跳转登录，没有凭证，所以无法截取登录后的工作区 |
| Round 5 文档（`docs/frontend/ROUND5_PROMPT.md`） | 按历史输入重新复测，结果见 §6.2 |

## 2. 现状矩阵

状态分四档：**已实现 / 部分实现 / 仅契约 / 不可用**。“之前”指 `eae35c4`，“之后”指本分支。
目前有两条会话路径：

- **旧 Web 路径**：Next.js `AgentChat` + FastAPI `/api/agent/*`，这是现在多用户线上实际使用的路径；
- **DSH 路径**：`harness/profile`，DeepSeek Harness Web 原生 Session，见 §3。

| 能力 | 之前 | 之后 | 代码位置 | 运行证据 | 仍存在的缺口 |
| --- | --- | --- | --- | --- | --- |
| 会话创建/继续 | 已实现（旧） | 已实现（旧） | `apps/api/routers/agent.py`、`components/agent-chat.tsx` | `test_agent_session_reliability.py`；E2E `agent-session-reliability` | DSH 路径：v0.3.3 已有每用户隔离 Host 的 session broker；v0.3.4 补上入口（独立子域 + Next 链接）、内核级 Host 隔离（systemd/docker launcher）、限流与审计、登出联动（全部默认关闭，§14）。尚未上线：需要 staging、真实模型 key 和部署侧出口限制 |
| 历史搜索/归档 | 不可用（后端已支持 `archived`，前端未用；没有搜索） | 部分实现：标题搜索在前端完成，归档/取消归档走服务端，失败时回滚 | 同上 | E2E `history: search, archive…` | 服务端全文搜索接口不存在 |
| 已删除会话 | **缺陷**：按 ID 仍可读、可继续发送 | 已修复：返回 404 | `agent_service.owned_conversation` | `test_a_deleted_conversation_cannot_be_read_or_continued` | — |
| 流式与重连 | 部分实现：轮询事件，但事件**从未应用到界面**；没有按 seq 去重 | 已实现（旧路径）：按 seq 去重、忽略其他 run 的帧、显示“连接中断/正在恢复”、按服务端记录给出结论 | `lib/agent-run-events.ts`、`agent-chat.tsx` | E2E dedup / reconnect / re-attach | 服务端在客户端断开时会把 run 标为 `interrupted`（不在后台继续），这是旧架构的限制。v0.3.4 的 mock 对照（§14）证实 DSH Session 断线不影响回合、重连后由 follow 快照收到完整回复 |
| 刷新恢复 | 不可用：忽略 `active_run_id` | 已实现：根据事件日志重新附着进行中的 run | `agent-chat.tsx#observeRun` | E2E `a reload re-attaches…` | 同上 |
| 重复提交 | **缺陷**：消息 POST 没有幂等键 | 已实现：`client_request_id`，重复时返回 409 `DUPLICATE_SUBMISSION` 并附着原 run；提供“安全重试” | `agent_service.start_run`、`agent.py` | pytest + E2E | — |
| 取消 | 已实现（停止生成） | 已实现，并明确说明“已执行的工具不会撤销，按实际用量结算”；同一 run 只取消一次 | 同上 | E2E `stop cancels…` | 聊天里没有后台任务；研究任务的取消在 `/research` |
| Skills | 部分实现：旧 SkillRegistry；DSH `ctx.skills` 只在 profile 中配置 | 已实现（只读展示）：研究设置里列出可用 Skill、适用场景、限定工具、是否需要确认、不可用原因，并说明“Skill 说明不会提升工具权限” | `chat-panels.tsx#SkillList`、`harness/profile/skills/*` | E2E `skills are listed…` | DSH Web 的 `/skill` 选择器只在 DSH 路径可用 |
| 图片附件 | 已实现 | 已实现，并增加上传进度 | `chat-workspace-composer.tsx` | E2E `harness-workspace` | Caddy 已在 `7f61371` 对 `/api/agent/attachments` 放行到 10 MiB，其余路径仍为 2 MB |
| 通用文件附件 | 仅 DSH profile 中禁用 | 不变（保持禁用） | `cordis.patch.yml` | public-profile-check | 需要先有会话级只读沙箱 provider |
| 研究任务 | 部分实现：SSE **读不到状态变化**（identity map） | 已修复 SSE；完整生命周期 `queued→…→completed/failed/canceled` | `routers/harness_runs.py` | `test_research_run_stream.py`（去掉修复后测试失败） | `HARNESS_RESEARCH_ENABLED` 默认关闭 |
| 证据引用 | 部分实现：只有来源 chip，`[n]` 不可点 | 已实现：`[n]` 链接到按需打开的证据 Inspector（抓取时间、新鲜度、缺口），可回跳到正文，焦点会返回 | `components/agent/evidence-inspector.tsx` | E2E `citation marker…` | 段落级锚点只到消息和引用标记粒度 |
| 产物 | 已实现（`/research/[runId]`） | 不变 | `research-run-detail.tsx` | — | 聊天内没有产物下载 |
| 模型路由 | 部分实现：菜单里有不可用模型，并硬编码 “DeepSeek V4 Pro” | 已实现：只列出当前可用且已定价的模型，显示 provider 和服务端给出的每轮预估；未列出的模型按原因（需升级套餐 / 未配置计价 / 不可用）计数说明（v0.3.3） | `agent-chat.tsx`、`agent.py`、`agent_service.py`、`packages/billing/metering.py` | `test_agent_model_pricing.py`；E2E `model-upgrade` | 没有显式费率的模型（目前 `gpt-6-*`）一律拒绝、不按默认费率计费；需由产品批准费率后通过 `AGENT_MODEL_CREDIT_RATES` 配置（§8） |
| 用量 | 已实现 | 已实现：发送前显示预估和预留，完成后显示实际扣费/退款（均为服务端值） | `agent-chat.tsx` | E2E `model-upgrade` billing | — |
| 工具审批 | 仅契约：`STATEFUL_TOOLS` 为空，审批流程不会触发；同时提供笼统的“自动执行” | 部分实现：“自动执行”已停用（服务端按 ask 执行）；审批卡显示动作/范围/影响/权限/有效期；服务端一次性、校验所有者、120 s 过期 | `chat_workspace.py`、`tool-approval-card.tsx` | pytest + E2E | 目前没有需要审批的有状态工具；DSH 公开 profile 中同样没有会走 `ask` 的工具，两条路径在出厂配置下都无法触发审批（§14） |
| 组合/NAV | 部分实现：没有账户时返回 **500**；`str(Decimal)` 输出 `0E-8` | 已实现：返回结构化 404；十进制字符串不再出现指数；界面标注口径、币种、版本、计算/价格时间和 stale | `routers/live_trading.py`、`decimal_text.py`、`NavPanel` | `test_live_trading_nav_http.py`；E2E | — |
| 回测 | 已实现（旧） | 不变 | `backtest-lab.tsx` | — | 尚未有 Harness UI 插件 |
| 领域 tool-view（Harness） | 仅契约：catalog 里的 `tool.*` UI 没有实现 | 已实现（Portfolio/NAV、Research、Options、Backtest、Memory）：`@puregamma/dsh-ui-portfolio`、`@puregamma/dsh-ui-research` 通过 `tool.call.toolview` 渲染工具结果的 `presentationMeta`（模型不可见），stale/unavailable/degraded 都会明确标出，缺失的 NAV 不显示为 0 | `harness/plugins/ui-{portfolio,research,options,backtest,memory}`、对应 `tool-*` | `domain-toolviews-check`（8 例） | 研究产物资源视图（`resource.research-artifact`）未做 |
| 全路由健壮性 | 不可用：`/daily-push` 在 API 故障时崩溃；`/secretary` 在桌面端横向滚动 | 已实现：51 个路由 × 桌面/手机在 API 不可用时不崩溃、不横向滚动，按钮/链接都有可访问名称 | `route-audit.spec.ts`（CI job） | 114/114 | — |
| 实盘 | 已实现（默认全部关闭），但界面在结果不明时允许重新预览、UNKNOWN 无解释、成交显示“不可用” | 已实现：审批卡、结果不明时只允许核对或重发**同一意图**、UNKNOWN 有解释、展示成交、可吊销连接。v0.3.4：用户侧 ledger/对账只读视图（Account 页不再显示“ledger 不可用”）、UNKNOWN 订单的同步状态与只查询的“请求重新核对”（默认关）、管理端审阅（kill switch、LIVE 资格、对账异常）、mandate 提案 → 双人审批 → 生效（默认关，迁移 0036）（§14） | `live-trading-console.tsx`、`admin-live-trading-console.tsx`、`packages/live_trading/{ledger_view,order_sync,admin_review,mandate_proposals}.py` | E2E `live-trading-workflow`、`live-trading-{ledger,recheck,admin}`；pytest `test_live_trading_*`（含 Postgres 并发） | 实盘开关仍由部署方控制，本次没有开启；mandate 提案只有 API、没有界面；`ledger.cash_balance` 仍跨币种求和（需单独评审风控语义） |
| 通知 | 已实现（旧） | 不变 | `routers/notifications.py` | — | — |
| 记忆 | 已实现（默认关闭） | 不变 | `routers/memory.py` | — | — |
| 移动端 | 部分实现：抽屉 Escape 后焦点不返回、导航抽屉关闭时仍可聚焦并漏出 12px、历史抽屉被页头遮挡 | 已实现：键盘与读屏可用，抽屉通过 portal 渲染、不透明，桌面折叠状态持久化 | `nav.tsx`、`agent-chat.tsx`、`use-dialog-focus.ts` | E2E `phone drawers` | — |

### 2.1 Catalog：目标能力与“已安装/健康/已授权”

`harness/plugins/catalog.ts` 只描述 23 个**目标**能力，不含安装状态和健康状态。按 `harness/profile/cordis.patch.yml` 统计，实际挂载的是 auth、billing、api-gateway、data-sources、admin、notifications、market-data、portfolio、research、options、backtest、memory、rsi-orchestrator、secretary、research-runner、pg-tsy-runtime 的 provider 与工具，以及 4 个 UI 插件。

**没有挂载**的有：trading、trading-mandates、trading-observation、nautilus-runtime、mobile-api、portfolio-autopilot、agent-chat。

“健康”和“已授权”只能在运行时判断：

- 每个 `*-legacy-api` provider 都用同一个 `PUREGAMMA_LEGACY_API_TOKEN` 调 FastAPI，**没有区分用户身份**；
- 所以在 DSH 路径上，“已授权”目前只能在单操作员前提下成立（§3）。

## 3. 架构取舍

1. **DSH Session 是目标主路径，但目前不能直接给多用户使用。** 固定版本的 DSH Web 有以下限制：
   - 只监听 loopback，用 launch-token 认证，单操作员；
   - 只有一个 Session 存储；
   - 会话列表（`sidebar.workspaces`，由 `ui-workspace` 提供）只能由 `ui-sidebar` 声明，并且依赖 Host 目录选择器（可列出、创建服务器目录）。

   在共享实例中打开它，所有用户会互相看到 Session 和服务器目录。所以：
   - `ui-sidebar` **保持禁用**，原因已写在 profile 注释里；
   - 恢复历史功能的前提是“每个用户一个隔离的 Host”，或者上游提供多租户支持。
   - v0.3.3：已实现“每个用户一个隔离的 Host”的 session broker（默认关闭），侧栏只在 broker 管理的单用户 Host 上通过 overlay 重新启用，基础 profile 不变（§13）。

   本次**没有**在 Next.js 新建持久会话状态机。旧聊天客户端只把服务端事件投影到界面（`lib/agent-run-events.ts` 是纯函数，不持久化），直到 DSH 路径具备多租户能力后退役。
2. **Profile 安全收口。** `@deepseek-ai/dsh-web-app` 还会插入 `ptc`、`minimal`、`cordis` 三个 preset。它们会暴露 bash/pwsh、PTY、任意文件读写、后台 job、subagent、workflow、ralph 和 plugin-manager 工具，用户只需切换 preset 就能拿到。本次全部禁用，并新增 `public-profile-check`：它解析上游 bundle 的 preset，叠加 profile 的覆盖，一旦出现上述工具就让 CI 失败（已用变异测试确认守卫有效）。
3. **Typert 网关。** `@puregamma/dsh-client-remotes` 之前只挂载了浏览器端，Host 端 `PureGammaClientGateway` 从未挂载。现在按上游做法（参照 `dsh-command-feedback`）在插件 `apply` 里挂载；Host 构建把 Cordis/Typert 设为 external，避免出现第二份 Cordis。说明：`ui-sidebar` 被禁用时，账户/计费/通知等设置区仍不可见（它们注册在 `settings.section`）。
4. **实盘只做审阅型改进。** 服务端已经保证：每个 intent 最多下一单（订单行带唯一 `order:{intent}` 键，在 mandate 行锁内提交）、UNKNOWN 只查询不重试、kill switch 不阻止撤单。本次界面只把这些事实如实呈现，不改风控和执行逻辑；UI 插件安装不会开启实盘。
5. **领域视图不打包进插件。** 没有把旧页面整体塞进 Harness 插件。旧页面继续作为兼容面，直到满足 `HARNESS_CORE_V2.md` 的逐项迁移门槛。

## 4. 迁移表（本次涉及项）

| 能力 | 旧入口 | 服务定义 | Provider | 权限/门槛 | UI slot | 测试 | 回滚点 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Agent 会话 | `/api/agent/conversations*`、`/runs/*` | DSH `ctx.remote.session` | DSH session-controller | 单操作员；**多租户阻塞** | `sidebar.workspaces`（禁用中） | `test_agent_session_reliability.py`、E2E | 回退 `240cc3f`、`c177d4d` |
| 工具审批 | `/api/agent/tool-calls/*/approval` | DSH `approval` 服务 | `dsh-user-approval` | 一次性、所有者、过期 | `conversation.composer` / `approval.detail` | `test_chat_workspace.py` | 回退 `c177d4d` |
| 研究 | `/api/research/runs*` | `pgResearch` | `research-legacy-api` | `HARNESS_RESEARCH_ENABLED` | 目标 `tool.research-run`（未实现） | `test_research_run_stream.py` | 回退 `c177d4d` |
| NAV | `/api/portfolio/nav*` | `pgPortfolio` | `portfolio-legacy-api` | 所有者；no-account 返回 404 | 目标 `tool.portfolio-nav`（未实现） | `test_live_trading_nav_http.py` | 回退 `c177d4d` |
| 实盘 | `/api/trading/*` | `pgTrading`（仅契约） | 未安装 | 静态 gate + 用户审批 + mandate + 风控 + 幂等 | 无（未挂载） | `live-trading-workflow.spec.ts` | 回退 `02d00da` |
| 账户/计费/通知 Remote | — | `puregammaClient` | `client-gateway` | release-boundary 白名单 | `settings.section` | `public-profile-check` | 回退 `aff15bb` |

## 5. 功能对照（截图见 `assets/agent-workspace-20261028/`）

| 场景 | 截图 |
| --- | --- |
| 桌面会话：历史搜索/归档、证据缺口按钮、内联审批卡、只列可用模型 | `chat-desktop-light.png` |
| 证据 Inspector：缺口、来源时间、过时标记、回到正文 | `chat-evidence-inspector-dark.png` |
| 手机历史抽屉（portal，不透明，可关闭） | `chat-phone-history-drawer.png` |
| 实盘审批卡（动作/范围/影响/权限/有效期） | `live-approval-card.png` |
| 实盘“提交结果未知”恢复 + UNKNOWN 横幅 | `live-unknown-result.png` |
| NAV 过期快照的口径与时间 | `live-overview-stale-nav.png` |
| 预览站公开页（视觉基线） | `preview-landing-desktop-light.png` |

## 6. 视觉核查

### 6.1 与预览站对比（视觉假设）

| 维度 | 预览站（公开页实测） | 本分支 |
| --- | --- | --- |
| 色彩与品牌 | 暖白/近黑的单色机构风；`data-visual-style=glass` | 不变，继续沿用仓库 token；主按钮改用 `--pg-surface-inverse` |
| 主题 | 浅色/深色首帧都正确（预渲染脚本） | 不变；新增 `darkMode` 选择器守卫 |
| 手机导航 | 关闭的抽屉在左侧漏出约 12px | 已修复 |
| 登录后的工作区 | **无法访问**（需要登录） | 按仓库 token 和组件实现，视为**视觉假设**，没有和线上做逐像素对比 |

### 6.2 Round 5 缺陷复测

| 编号 | 复测结果 |
| --- | --- |
| D1 反色按钮 | **仍存在**（30 行），本次修复 |
| D2 Markdown 无样式 | 已在 `main` 修复；`markdown-render` 的 h1 断言量错了元素（量到页头 h1），本次修正 |
| D3 Focus | 已在 `main` 修复 |
| D4 两条路由宽度不一致 | 已在 `main` 修复 |
| D5 移动端历史 | `main` 有抽屉，但存在焦点/遮挡问题，本次修复 |
| D6 长内容裁切 | 已在 `main` 修复 |
| D7 `useHtmlDataset` | 已在 `main` 修复 |
| D8/D9/D10 | 已在 `main` 修复（`color-scheme`、未定义变量） |
| Tailwind `darkMode` 未配置 | **仍存在**，本次修复 |
| composer 在 1280×720 下落到首屏以下 | **仍存在**（`harness-workspace` 在 `main` 上失败），本次修复 |

## 7. 测试证据（本机实测）

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` | 见 PR 描述（全部通过） |
| 后端 CI lint | `ruff check apps packages services scripts tests --select E9,F63,F7,F82` | 通过 |
| Harness | `pnpm --dir harness run check`（含新增 public-profile-check） | 通过 |
| Web | `pnpm typecheck`、`pnpm lint`（警告数量与基线相同）、`pnpm build`（CI 环境变量） | 通过 |
| 全路由审计 | `next build` + `next start`，然后运行 `playwright test route-audit.spec.ts`（API 不可用） | 114/114 通过（v0.3.1） |
| Harness 领域视图 | `pnpm --dir harness run check`（含 `domain-toolviews-check`） | 通过（v0.3.1） |
| E2E（本次相关） | `agent-session-reliability`、`chat-design`、`harness-workspace`、`markdown-render`、`live-trading`、`live-trading-workflow`（chromium + mobile-chrome） | 全部通过 |
| E2E（其余） | theme、visual-style、contrast、i18n、portfolio、dashboard、plugins、mobile-fixes、nautilus、model-upgrade 首页段 | 与 `main` 基线**失败集合完全相同**（这些用例依赖生产 API；本机把代理指向了不可达端口，避免测试流量打到生产） |

环境说明：

- 本机 Playwright 使用系统 Chromium；
- 有些 spec 的路由 stub 写死了 `127.0.0.1:3000`，在其他端口运行时必须同时设置 `PLAYWRIGHT_BASE_URL`；
- `mobile-nav.spec.ts` 描述的“底部导航”在应用里不存在，这个 spec 本身已过期，未纳入。

## 8. 尚未上线 / 已知缺口

- **实盘与账务（v0.3.4，§14）**：新增的写入口全部默认关闭——`LIVE_ORDER_RECHECK_ENABLED`（只查询的重新核对）、`LIVE_MANDATE_PROPOSALS_ENABLED`（需先在生产执行迁移 0036）。是否开启、审批人范围、限流间隔、`LIVE_ORDER_SYNC` 审计行的保留策略需要产品决定。管理端 `notes` 改为必填、释放不存在的 kill switch 返回 404，仓库外的脚本需同步。
- **DSH 多租户**：v0.3.3 实现了每用户隔离 Host 的 session broker；v0.3.4 补上入口、内核级 Host 隔离、限流审计和登出联动（均默认关闭，§14，上线步骤见 [runbook](upgrade-20261029/dsh-ingress-isolation.md) §5）。仍未上线：需要用户决定上线时间与 `HARNESS_DOMAIN`、提供 staging 与真实模型 key、两个测试账号、选择出口限制方案（user manager 会忽略 `IPAddressDeny`）；硬性磁盘配额、broker 的 systemd 服务文件和 docker 镜像属于部署工作；CSP 仍需 `'unsafe-eval'`（上游限制）。
- **Harness 编译依赖对齐**：v0.3.3 已把 npm 上的 `@deepseek-ai/*` 升到 `0.1.7-rc.1`（与 vendored gitlink 同 tag）。vendored 源码本身没有在本机构建（磁盘和内存不足），用的是同 tag 的 npm 包。
- **领域 tool-view 插件**：五个领域都已实现（v0.3.1–v0.3.2）。研究产物和回测产物的资源视图（`resource.*`）尚未实现。
- **计费**：v0.3.3 起没有显式费率的模型直接拒绝（`AGENT_MODEL_PRICING_NOT_CONFIGURED`），不再按默认费率计费；代码里没有新增任何价格。`gpt-6-luna/sol/astra` 因此在菜单中显示“未配置计价”，需要产品批准费率后通过 `AGENT_MODEL_CREDIT_RATES` 配置。
- **上传上限**：已在 `7f61371` 统一（`/api/agent/attachments` 放行到 10 MiB，其余路径保持 2 MB）；需要随下次部署生效。
- **有状态工具**：`STATEFUL_TOOLS` 为空，审批卡目前只能通过 stub 和已有的待审批记录验证。
- **外部 MCP 和子任务**：没有实现。原因：没有可分解的真实任务，底层也不支持多租户，按要求不添加装饰性界面。

## 9. Codex 运行时插件可行性评估

依据 OpenAI 官方文档（2026-10-28 查阅，`developers.openai.com/codex/*` 已重定向到 `learn.chatgpt.com/docs/*`）：

- app-server 文档原文：“App-server authentication has never been permitted for commercial or hosted services.”
- 商业/托管场景需要 **Sign in with ChatGPT** 合作伙伴通道（目前为有限试用，需要申请）。
- CLI 凭证（`~/.codex/auth.json`）只允许在自己的可信私有机器上使用，并且“不要在多台机器或并发任务之间共享”。
- 用户条款禁止共享账号凭证。

结论：PureGamma 作为多用户托管服务，**目前没有合规方式**让用户用自己的 ChatGPT/Codex 登录在服务器上运行 Codex，所以本次**没有实现** Codex provider，也没有复制任何本机凭证。

合规的替代方案有两种：

- 用户自带 API key：服务端加密存储，每次运行注入到隔离的 `CODEX_HOME`，费用记在用户自己的组织；
- PureGamma 组织 API key：配合按用户的 `safety_identifier` 和配额。

如果将来获得 Sign in with ChatGPT 合作资格，需要满足：

- 每个用户单独完成 OAuth 授权；
- token 只存在服务端，刷新操作串行化；
- 界面标注“使用 ChatGPT 套餐”。

## 10. 回滚

- 每个阶段都是独立提交（harness → api → live-trading → agent → nav → web global → docs），可以用 `git revert <sha>` 单独回退。
- **数据库**：没有迁移。`client_request_id` 存放在已有的 `AgentMessage.context_json` 中，回滚后旧代码会忽略它。
- **API 兼容性**：
  - 新增：`client_request_id`（可选）、事件里的 `at` / 脱敏后的 `arguments`、`latencyMs`；
  - 行为变化：`full-access` 按 `workspace-write` 执行；no-account 时返回 404 而不是 500；已删除会话返回 404。
  - 旧版移动端发送 `full-access` 仍会被接受，并保存为 `workspace-write`。
- **Profile**：若需要恢复被禁用的 preset，删除 `cordis.patch.yml` 中三条 `disabled: true` 即可。但这会重新暴露 shell/文件工具，**不建议**在公开实例中这样做。

## 11. v0.3.1 追加

- 全路由审计：修复 `/daily-push` 在 API 故障时的崩溃，以及 `/secretary` 在桌面端的横向滚动；审计已加入 CI。
- Skills 只读面板；上传遇到边缘代理返回的 413 时，按“超出大小限制”提示。
- Harness 领域 tool-view 插件（Portfolio/NAV、Research），数据来自 `presentationMeta`。

## 12. v0.3.2 追加

- `@puregamma/dsh-ui-options`：标明“仅研究，执行已禁用”，显示数据源状态（degraded/unavailable）和返回条目数。
- `@puregamma/dsh-ui-backtest`：原样显示服务端上报的指标，并标注“基于历史数据的模拟，不是预测或交易信号”。
- `@puregamma/dsh-ui-memory`：只显示种类和条目数，不显示记忆内容（隐私）。
- 对应 tool 插件通过 `presentationMeta` 输出 v1 DTO（模型不可见）；`domain-toolviews-check` 扩展到 8 例。

## 13. v0.3.3 追加

v0.3.2 之后合入 `main` 的变更（均未执行生产部署、数据库迁移、切流或实盘开启）：

- `588b386`：LIVE mandate 暂停后可以恢复；控制台解释被阻止的门禁。
- `7f61371`：Caddy 对 `/api/agent/attachments` 放行到 10 MiB，其余路径仍为 2 MB。
- `4d2cf70`：PAPER/SHADOW 运行时控制台不再把缺失数据显示为 0。
- DSH 多租户（`150a0c3`…`61e4e56`，详见 [upgrade-20261028/dsh-multi-tenant.md](upgrade-20261028/dsh-multi-tenant.md)）：
  - npm 上的 `@deepseek-ai/*` 对齐到 `0.1.7-rc.1`，tool view 改为按 phase 渲染；
  - session broker：每个 PureGamma 用户一个隔离的 DSH Web Host，认证在查找 Host 之前完成，不会回退到其他 Host；`PUREGAMMA_DSH_BROKER_ENABLED` 默认关闭；
  - FastAPI `POST /internal/dsh/host-tokens`：需要 broker 密钥加用户本人凭证，token ≤15 分钟、只作 Bearer、路由白名单、登出即失效；`DSH_MULTI_TENANT_ENABLED` 默认关闭；
  - 沙箱目录选择器（只在用户 root 内，不能创建目录，未配置 root 时一律失败）；多租户 overlay 只在 broker 管理的单用户 Host 上重新启用 `ui-sidebar`/`ui-workspace`，**基础 profile 仍然禁用侧栏**，shell/文件/终端/plugin-manager/通用上传保持禁用；
  - 修复 `main` 上已有的问题：PureGamma profile 禁用 `file-upload` 后原生 Session Controller 从未激活，现由拒绝一切的 `fileUploads` provider 补上；
  - Codex guard：没有 profile 行挂载 Codex/ChatGPT 登录 provider，仓库代码不读取 Codex CLI 凭证（§9 结论不变）。
- E2E 与模型计价（`3a7f2bc`…`6ee50b7`，详见 [upgrade-20261028/e2e-and-model-pricing.md](upgrade-20261028/e2e-and-model-pricing.md)）：
  - 模型显式费率，未定价即拒绝（报价、预留、结算一致）；`/api/agent/capabilities` 返回 provider、能力、每轮预估和限制；菜单显示 provider 和预估，不再提供只做评估的 Jev；
  - Playwright 全量离线化（SSR fixture API、只解析回环地址的浏览器），过期 spec 按当前行为改写；CI 新增全量 4 分片和 auth-guard job。
  - CI 稳定性（`3c5a9d8`、`2d4af59`、`63fa2a0`）：contrast-audit 在取样前等待页面内容就绪（有上限，阈值不变）；CI 上失败重试一次，只在重试后通过的用例由 `report-flaky.mjs` 以 warning 注释和 job summary 列出，确定性失败仍然失败。

验证（协调会话在 rebase 后的树上复跑，另附各工作会话的报告）：

| 项目 | 结果 |
| --- | --- |
| `pnpm --dir harness run check`（含 legacy-auth、session-broker、directory-picker、codex-guard、public-profile、domain-toolviews） | 通过 |
| `pytest tests`（合并后全量） | 1295 项，0 失败，7 跳过 |
| `apps/web` typecheck / lint | 通过（9 个已有警告） |
| Playwright（model-upgrade、billing、agent-session-reliability、visual-style × chromium + mobile-chrome） | 84 通过 |
| 工作会话报告：真实 DSH `0.1.7-rc.1` 两个 Host 的隔离集成测试 | 9/9（未认证 401、A/B Session 互不可见、选择器越界被拒、跨站 403） |
| 工作会话报告：Playwright 全量（除 route-audit）× 2 端 | 300 通过、0 失败、8 跳过（live-only）；route-audit 114/114 |
| GitHub Actions（Harness、Commercial Release Gate、commercial readiness、Web E2E） | 见 v0.3.3 release 对应提交 |

## 14. v0.3.4 追加

v0.3.3 之后合入 `main` 的变更（均未执行生产部署、生产数据库迁移、切流或实盘开启；新能力默认关闭）：

- **实盘与账务可审计**（`68833f7`…`0186a72`，详见 [upgrade-20261029/live-ledger-audit.md](upgrade-20261029/live-ledger-audit.md)）：
  - 用户侧 ledger 与对账只读接口（`GET /api/trading/ledger`、`/reconciliation`）：先按所有权解析，他人与不存在一律 404；keyset 分页（`created_at DESC, id DESC`，游标不携带权限）；金额为十进制字符串；没有数据显示 `empty`/不可用，不显示 0。Account 页接入。
  - UNKNOWN 订单同步状态（`GET /orders/{id}/sync-status`）与只查询的“请求重新核对”（`LIVE_ORDER_RECHECK_ENABLED`，默认关；每单限流，在订单行锁内先记录再查询；kill switch 期间仍可查询）。后台同步在结果变化时追加 `LIVE_ORDER_SYNC` 审计行（只追加、与状态更新同一事务，不受开关控制）。
  - 管理端审阅页 `/admin/trading`：kill switch 启用/释放（原因必填、二次确认）、LIVE 资格审批（不能自批）、对账异常审阅；全部由服务端 `admin_user` 授权。
  - Mandate 提案 → 两名不同管理员审批（提案人和所有者都不能批）→ 生效（生效后处于暂停状态，仍经过全部静态门禁）。`LIVE_MANDATE_PROPOSALS_ENABLED` 默认关；新表来自只增不改的迁移 0036，迁移未执行时接口返回“不可用”，其他路径不访问新表。
  - 测试中发现并修复的既有缺陷：暂停/恢复与撤单的审计键精确到秒，同一秒内的第二次操作审计被去重丢失；并发确认的输家拿到锁后未复查，可能把已批准的 intent 改成 REJECTED；撤单返回 `CANCEL_UNKNOWN` 时界面仍显示“已撤单”。

- **DSH 多租户上线准备**（`933da85`…`080c5ee`，详见 [upgrade-20261029/dsh-ingress-isolation.md](upgrade-20261029/dsh-ingress-isolation.md)，含上线 runbook、回滚和更新后的威胁模型）：
  - 先修两个真实浏览器才暴露的阻断问题：v0.3.3 的多租户 UI 实际打不开——浏览器端 Session controller 也依赖 `fileUpload`（拒绝型插件新增 client face），以及 broker 用 `URLSearchParams` 删 token 时破坏了 DSH 的合并 URL `plugins/??a,b`。
  - 入口：DSH Web 可以挂在路径前缀下（实测），但生产推荐独立子域（DSH 需要 `'unsafe-eval'`，不应与主站同源）。Caddy 站点只通过 `docker-compose.harness-sessions.yml` 加载，生产 `Caddyfile` 未改且 CI 守卫；Next 链接由 `NEXT_PUBLIC_DSH_SESSIONS_URL` 控制，默认不出现。broker 对每个响应加 CSP 与安全头。
  - Host 隔离：可插拔 launcher（`direct` 默认 / `systemd` user transient unit / `docker`），内存、CPU、进程数、文件描述符、单文件大小上限，用户目录软配额（超限 507），只能看到本用户目录；每用户私有 profile 目录（DSH 启动时会重写 `cordis.yml`，v0.3.3 的软链接让所有租户写同一文件）；关闭共享 `/tmp` 的原生扩展缓存。
  - 限流与审计：每用户令牌桶、在途请求与 WebSocket 上限、按地址的身份查询限流、全局 Host 启动速率（429 + `Retry-After`）；JSON 审计行（user 为 HMAC，含 session/plugin/provider/trace，不记录 prompt/cookie/token）；`traceparent`/`X-Request-Id` 透传给 Host 与 FastAPI。
  - 登出联动：FastAPI `DSH_BROKER_REVOKE_URL`（默认关）在登出后通知 broker 关闭隧道并停止 Host；broker 另外每 60 s 复查已打开的隧道（补上 v0.3.3“登出后 WebSocket 隧道仍可用”的缺口）。
  - 端到端对照（本地确定性 mock 模型，**不是真实 key**）：DSH 与旧 Web 路径各 10 个场景，19 通过、0 失败，DSH“工具审批”为缺失（两条路径出厂配置下都无法触发）。DSH 在刷新恢复、断线重连、归档后阻止新回合上优于旧路径；首次跑通“模型工具调用 → legacy-api provider → 用户 Host token → FastAPI”链路；图片走内联，不需要上传 provider。

验证（协调会话在合并前的树上复跑，另附工作会话报告）：

| 项目 | 结果 |
| --- | --- |
| `pytest tests`（`0186a72`，heavy 锁 + 2000M scope） | 1377 通过、9 跳过、4 xfailed、0 失败 |
| Postgres（一次性 `postgres:17` 容器，`PUREGAMMA_TEST_POSTGRES_DSN`） | `test_live_trading_ledger_postgres.py` + `test_live_trading_concurrency_postgres.py`：8/8，连跑 2 次 |
| ruff（CI 规则） | 通过 |
| `apps/web` typecheck / lint | 通过（9 个已有警告） |
| Playwright（生产构建 + `next start`，chromium + mobile-chrome） | live-trading-ledger 12、live-trading-recheck 10、live-trading-admin 16、live-trading-workflow 24，全部通过 |
| 工作会话报告：route-audit（生产构建） | 116/116（新增 `/admin/trading`） |
| 工作会话报告：变异测试 | 16 项守卫去掉后对应测试失败（所有权、只读保证、限流、自批、双人审批、审计键、锁内复查等） |
| W1 rebase 到 `main` 后：`pnpm run check`（harness，pnpm 11.7.0） | 90 通过、0 失败、3 跳过（需要真实 caddy/docker 的 live 用例在协调环境跳过；工作会话报告带真实 caddy 与 docker 时全部通过） |
| W1 rebase 后：`pytest tests` / ruff / web typecheck / lint | 1383 通过、9 跳过、4 xfailed、0 失败 / 通过 / 通过 / 9 个已有警告 |
| W1 rebase 后：Playwright（生产构建） | harness-sessions-entry 2 通过（开关关闭；开启用例按设计跳过）、chat-design 10 通过；agent-session-reliability 28 通过、2 失败——同样的 2 项在不含 W1 的 `main` 生产构建上也失败（手机历史抽屉选择会话后焦点未返回），CI 的 dev 模式通过，列为遗留项 |
| 工作会话报告：真实 DSH `0.1.7-rc.1` | direct 13/13；systemd、docker launcher 各 12/12（浏览器、上限回读、目录隔离、空闲回收）；根路径与 `/harness` 前缀下浏览器均正常 |
| 工作会话报告：端到端对照（mock 模型 + 一次性 Postgres） | 19 通过、0 失败，DSH 工具审批为缺失 |

合并时发现并修复：`0186a72` 新增的 `/admin/trading` 页面没有登记到 Harness 迁移台账，`architecture-check` 因此失败；harness-v2 CI 只在 `harness/**` 变化时运行，所以 `main` 上没有暴露（`1fb1da7` 补登记，owner `admin`）。

