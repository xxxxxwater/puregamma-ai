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
| 会话创建/继续 | 已实现（旧） | 已实现（旧） | `apps/api/routers/agent.py`、`components/agent-chat.tsx` | `test_agent_session_reliability.py`；E2E `agent-session-reliability` | DSH 路径缺多租户（§3） |
| 历史搜索/归档 | 不可用（后端已支持 `archived`，前端未用；没有搜索） | 部分实现：标题搜索在前端完成，归档/取消归档走服务端，失败时回滚 | 同上 | E2E `history: search, archive…` | 服务端全文搜索接口不存在 |
| 已删除会话 | **缺陷**：按 ID 仍可读、可继续发送 | 已修复：返回 404 | `agent_service.owned_conversation` | `test_a_deleted_conversation_cannot_be_read_or_continued` | — |
| 流式与重连 | 部分实现：轮询事件，但事件**从未应用到界面**；没有按 seq 去重 | 已实现（旧路径）：按 seq 去重、忽略其他 run 的帧、显示“连接中断/正在恢复”、按服务端记录给出结论 | `lib/agent-run-events.ts`、`agent-chat.tsx` | E2E dedup / reconnect / re-attach | 服务端在客户端断开时会把 run 标为 `interrupted`（不在后台继续），这是旧架构的限制，由 DSH Session 解决 |
| 刷新恢复 | 不可用：忽略 `active_run_id` | 已实现：根据事件日志重新附着进行中的 run | `agent-chat.tsx#observeRun` | E2E `a reload re-attaches…` | 同上 |
| 重复提交 | **缺陷**：消息 POST 没有幂等键 | 已实现：`client_request_id`，重复时返回 409 `DUPLICATE_SUBMISSION` 并附着原 run；提供“安全重试” | `agent_service.start_run`、`agent.py` | pytest + E2E | — |
| 取消 | 已实现（停止生成） | 已实现，并明确说明“已执行的工具不会撤销，按实际用量结算”；同一 run 只取消一次 | 同上 | E2E `stop cancels…` | 聊天里没有后台任务；研究任务的取消在 `/research` |
| Skills | 部分实现：旧 SkillRegistry；DSH `ctx.skills` 只在 profile 中配置 | 已实现（只读展示）：研究设置里列出可用 Skill、适用场景、限定工具、是否需要确认、不可用原因，并说明“Skill 说明不会提升工具权限” | `chat-panels.tsx#SkillList`、`harness/profile/skills/*` | E2E `skills are listed…` | DSH Web 的 `/skill` 选择器只在 DSH 路径可用 |
| 图片附件 | 已实现 | 已实现，并增加上传进度 | `chat-workspace-composer.tsx` | E2E `harness-workspace` | Caddy 限制 2 MB，应用允许 10 MB（§8） |
| 通用文件附件 | 仅 DSH profile 中禁用 | 不变（保持禁用） | `cordis.patch.yml` | public-profile-check | 需要先有会话级只读沙箱 provider |
| 研究任务 | 部分实现：SSE **读不到状态变化**（identity map） | 已修复 SSE；完整生命周期 `queued→…→completed/failed/canceled` | `routers/harness_runs.py` | `test_research_run_stream.py`（去掉修复后测试失败） | `HARNESS_RESEARCH_ENABLED` 默认关闭 |
| 证据引用 | 部分实现：只有来源 chip，`[n]` 不可点 | 已实现：`[n]` 链接到按需打开的证据 Inspector（抓取时间、新鲜度、缺口），可回跳到正文，焦点会返回 | `components/agent/evidence-inspector.tsx` | E2E `citation marker…` | 段落级锚点只到消息和引用标记粒度 |
| 产物 | 已实现（`/research/[runId]`） | 不变 | `research-run-detail.tsx` | — | 聊天内没有产物下载 |
| 模型路由 | 部分实现：菜单里有不可用模型，并硬编码 “DeepSeek V4 Pro” | 已实现：只列出当前可用的模型（含 provider），另注明有几个受套餐限制 | `agent-chat.tsx`、`agent.py` | E2E `model-upgrade` | 后端 `MODEL_RATES` 只认 `gpt-5.6-luna`，`gpt-6-*` 按默认费率计费（§8，未改动计价） |
| 用量 | 已实现 | 已实现：发送前显示预估和预留，完成后显示实际扣费/退款（均为服务端值） | `agent-chat.tsx` | E2E `model-upgrade` billing | — |
| 工具审批 | 仅契约：`STATEFUL_TOOLS` 为空，审批流程不会触发；同时提供笼统的“自动执行” | 部分实现：“自动执行”已停用（服务端按 ask 执行）；审批卡显示动作/范围/影响/权限/有效期；服务端一次性、校验所有者、120 s 过期 | `chat_workspace.py`、`tool-approval-card.tsx` | pytest + E2E | 目前没有需要审批的有状态工具 |
| 组合/NAV | 部分实现：没有账户时返回 **500**；`str(Decimal)` 输出 `0E-8` | 已实现：返回结构化 404；十进制字符串不再出现指数；界面标注口径、币种、版本、计算/价格时间和 stale | `routers/live_trading.py`、`decimal_text.py`、`NavPanel` | `test_live_trading_nav_http.py`；E2E | — |
| 回测 | 已实现（旧） | 不变 | `backtest-lab.tsx` | — | 尚未有 Harness UI 插件 |
| 领域 tool-view（Harness） | 仅契约：catalog 里的 `tool.*` UI 没有实现 | 已实现（Portfolio/NAV、Research）：`@puregamma/dsh-ui-portfolio`、`@puregamma/dsh-ui-research` 通过 `tool.call.toolview` 渲染工具结果的 `presentationMeta`（模型不可见），stale/unavailable/degraded 都会明确标出，缺失的 NAV 不显示为 0 | `harness/plugins/ui-portfolio`、`ui-research`、`tool-portfolio`、`tool-research` | `domain-toolviews-check`（5 例） | Options/Backtest/Memory 视图未做 |
| 全路由健壮性 | 不可用：`/daily-push` 在 API 故障时崩溃；`/secretary` 在桌面端横向滚动 | 已实现：51 个路由 × 桌面/手机在 API 不可用时不崩溃、不横向滚动，按钮/链接都有可访问名称 | `route-audit.spec.ts`（CI job） | 114/114 | — |
| 实盘 | 已实现（默认全部关闭），但界面在结果不明时允许重新预览、UNKNOWN 无解释、成交显示“不可用” | 已实现：审批卡、结果不明时只允许核对或重发**同一意图**、UNKNOWN 有解释、展示成交、可吊销连接 | `live-trading-console.tsx` | E2E `live-trading-workflow`（15 例 × 2 端） | 实盘开关仍由部署方控制，本次没有开启 |
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

- **DSH 多租户**：需要每用户一个隔离 Host，或上游多租户支持；provider 也要能透传每个用户的身份。
- **Harness 编译依赖对齐**：`@deepseek-ai/*` 从 `0.1.5-rc.2` 升到与 vendored `0.1.7-rc.1` 一致，需要单独评估。
- **领域 tool-view 插件**：Portfolio/NAV 和 Research 已实现（v0.3.1）；Options、Backtest、Memory 的视图以及 `tool.research-run` 资源视图尚未实现。
- **计费**：`MODEL_RATES` 和 gpt-6 系列模型不匹配。涉及价格，本次没有改，需要产品确认。
- **上传上限**：Caddy 限制 2 MB，应用允许 10 MB，需要部署侧统一。
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
