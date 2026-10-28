# E2E 全量离线化与模型计价（2026-10-28）

状态：代码与测试已完成，**未执行任何生产部署、数据库迁移、切流或实盘开启**。
分支：`upgrade/e2e-and-model-pricing`。

本文分两部分：

- 第一部分：整套 Playwright 用例在离线环境（无真实 API）下全部通过，并在 CI 中全量运行；
- 第二部分：Agent 模型菜单与计价——每个可选模型都必须有显式费率，否则拒绝（fail closed）。

---

## 一、Playwright 全量离线化

### 1.1 离线基础设施

| 组件 | 作用 |
| --- | --- |
| 浏览器请求 | 仍由各 spec 的 `page.route()` stub；未 stub 的 `/__dev-api/*` 经 dev 代理打到关闭端口（`DEV_API_PROXY_TARGET=http://127.0.0.1:9`），表现为接口故障 |
| 服务端渲染（SSR）请求 | **新增** `tests/e2e/playwright/fixtures/ssr-api.mjs`：`playwright.config.ts` 通过 `webServer` 启动它，并以 `PUREGAMMA_SERVER_API_URL` 指给 Next 服务端。只有列出的路径返回仓库内的 fixture；其余请求无凭证时返回 401（与真实 API 对匿名请求一致），带凭证时返回 503。需要“已登录”服务端页面的 spec 设置 cookie `pg_session=playwright-fixture-session`，带 `auth: true` 的 fixture 只对这个会话返回数据 |
| 第三方请求 | **新增**：浏览器启动参数 `--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost`，只解析回环地址；Hyperliquid 行情、CDN、统计脚本等外部请求立即失败，页面必须显示不可用状态。`PLAYWRIGHT_ALLOW_EXTERNAL=1` 可关闭 |
| dev 服务器稳定性 | **新增** `playwright.global-setup.ts`：首个用例前预编译错误页（`/_error`）；`next.config.js` 仅在 `PLAYWRIGHT_DEV_SERVER=1`（测试服务器）时让已编译页面常驻，避免测试中途重新编译。见 1.3 |
| 端口 | 不再写死 `127.0.0.1:3000`：spec 使用 `PLAYWRIGHT_BASE_URL` 或通配路由 |

### 1.2 逐个 spec 的分类

分类：**过期**＝断言描述的界面/文案已不存在，按当前预期行为改写；**缺 stub**＝依赖真实 API，补 fixture/stub；**产品缺陷**＝修改应用并有测试覆盖；**基础设施**＝测试环境问题。

| Spec | 分类 | 处理 |
| --- | --- | --- |
| admin-console | 缺 stub | 服务端 admin 读取原来打到线上（401→“需要管理员权限”）。现由 SSR fixture API 对匿名请求返回 401，同一路径 |
| admin | 过期 | 旧的“Operational Control Room”单页已被分区后台替代。改为：未登录跳转登录页（带 `returnTo`）；非管理员看不到后台分区 |
| agent-session-reliability、chat-design、harness-workspace、markdown-render | 原本通过 | 不变 |
| architecture-visual | 过期 + 产品缺陷 | 徽标由“在线”改为“系统示意”（静态示意图不应声称在线）。另：窗口标题 `PUREGAMMA.AI` 写死 `text-slate-300`，浅色主题对比度 1.48:1，改为主题 token `text-text-pg-muted`（由 contrast-audit 发现） |
| billing | 占位 fixme | 空的 `test.fixme` 改为真实用例：聊天发送遇到 402 `INSUFFICIENT_CREDITS` 时跳转到用户语言下的 `/billing`（`lib/api.ts` 的现有约定） |
| contrast-audit | 产品缺陷 + 缺 stub + 测量稳健性 | 修复上述标题对比度；API 文档页补 catalog stub；采样等待有限动画结束（入场动画期间文字透明度 <0.6 会被跳过，导致两次采样“一致”却测不到内容）。断言阈值不变 |
| daily-push | 过期 + 缺 stub | 旧用例假定所有访客都预选 iMessage。改为：无设置数据时不显示可能覆盖真实设置的表单；登录（fixture）后 Pro 用户只看到套餐包含的渠道，测试发送写入投递记录 |
| dashboard | 过期 | 旧标题（“Decide what matters today.”等）已不存在。改为：API 不可用时显示 WAITING、账户/计费不可用、无研究简报的空状态，不编造数据（中英文） |
| i18n | 过期 | 首页主标题、控制台不再有余额卡、每日推送页不再渲染示例简报；手机端语言切换在导航抽屉里 |
| integrations | 过期 + 缺 stub | 页面不再用演示连接器冒充真实状态。改为：无数据时显示“连接状态暂不可用”且没有演示卡片；登录（fixture）后只显示 API 返回的连接，并显示连接错误 |
| live-chat-workspace | 仅线上验收 | 设计上需要 `LIVE_TOKEN` 并访问生产环境；离线套件中按设计跳过（运行它就会访问生产 API，违反约束） |
| live-trading、live-trading-workflow | 原本通过 | 不变（不在本工作范围内修改） |
| mobile-fixes | 缺 stub | API 文档页的 catalog 在浏览器端读取，补 fixture，表格宽度约束在真实行上测量 |
| mobile-nav | 过期 | 应用没有底部导航，也没有 “Voice Secretary” 链接。改写为：手机端菜单按钮打开“Primary navigation”对话框并逐项跳转（中英文）；聊天历史抽屉只在打开时是 “Conversation history” 对话框，Escape 关闭并归还焦点；断点间侧栏与菜单按钮互斥；主要页面无横向滚动 |
| model-upgrade | 缺 stub + 过期 + 第二部分 | 首页公告/模型卡来自 SSR catalog fixture；代码示例只给可调用模型（`77a08f8` 的产品决定），GLM 5.2 显示“调用尚未开放”；Gateway 控制台拆为未登录不可用状态 + fixture 登录后的用量/请求/余额行；Agent 菜单段见第二部分 |
| mstr-btc | 过期（页面从未入库） | `opportunities/mstr-btc` 页面在仓库任何版本中都不存在（只有 spec 随生产同步提交进入），“Opportunities” 导航也已移除。改为固定当前契约：该地址返回 404，且不渲染半成品研究视图。若将来恢复该页面，需同时恢复原断言 |
| nautilus | 过期 | 页面现在有两处 “LIVE DISABLED”（头部徽标 + 内嵌实盘安全面板），改为明确断言两处及面板说明 |
| plugins-runtime、theme-system | 原本通过 | 不变 |
| portfolio | 过期 | 连接按钮是**有意**启用的（未配置时卡片标 NEEDS CONFIG，点击说明原因）。改为断言说明文案，且不会请求 link-token |
| public-page-access | 原本通过 + 新 CI job | “受保护页面需要会话”的 4 个用例需要 `REQUIRE_AUTH=true` 的服务器，在套件服务器中按设计跳过；新增 CI job `auth-guard` 专门运行 |
| route-audit | 原本通过 | 生产构建 + `next start`，保持原 CI job |
| visual-style | 过期 + 基础设施 | 默认主题是“跟随系统”而非固定深色；手机端外观控件在导航抽屉里；原“仅手机”的溢出检查在两个项目上都成立，去掉 skip。另见 1.3 |

### 1.3 dev 服务器中途编译导致的超时

现象：偶发的 `page.goto` 等不到 `load`、或页面不水合（例如 visual-style 刷新后外观按钮停在服务端默认状态）。trace 显示页面自身的 JS chunk 一直没有响应；同一时刻 dev 日志在编译 `/_error`——第一次有未 stub 的接口经代理返回 500 时，Next 才编译 pages router 的错误页。处理：

- `globalSetup` 在第一个用例前请求 `/__dev-api/warmup` 和一个不存在的路径，提前编译错误页；
- 测试 dev 服务器上让已编译页面常驻（`onDemandEntries`），避免空闲 60 秒后被回收再在测试中重编译；
- **没有**预编译全部路由：在 8 GB 共享机器上试过，dev 服务器超过 3 GB，导致整机内存不足（`warm-dev-server.mjs --all` 仅供内存充足的机器使用）。

### 1.4 CI（`.github/workflows/web-e2e.yml`）

| Job | 内容 |
| --- | --- |
| `e2e`（原有） | 6 个核心 spec，保持不变 |
| `full-suite`（新增） | 全部 spec × chromium + mobile-chrome，`--shard=1..4/4`，每片 `timeout-minutes: 25`，排除 route-audit（按标题 `--grep-invert`） |
| `auth-guard`（新增） | 以 `REQUIRE_AUTH=true` 启动 dev 服务器，只跑 public-page-access 的受保护页面用例 |
| `route-audit`（原有） | 生产构建 + `next start`，不变 |



## 二、模型菜单与计价

### 2.1 问题

| 位置 | 之前的行为 |
| --- | --- |
| `packages/billing/metering.py` `MODEL_RATES` | 只有 `default` 和 `gpt-5.6-luna` 两个条目；查不到的模型一律回落到 `default` 费率 |
| `apps/api/config.py` `OPENAI_AGENT_MODELS` | 默认提供 `gpt-6-luna / gpt-6-sol / gpt-6-astra` |
| 结果 | 这三个模型能被选择、报价、预留和结算，但用的都是**隐式的平台默认费率**，没有任何地方批准过这个价格 |
| 结算 | 按 provider 回显的 `response_model` 查费率；即使选择的模型有价格，回显带日期的快照名（如 `gpt-5.6-luna-2026-09-14`）时也会落到默认费率 |
| `agent_model_options` | `credit_cost: None`，菜单无法给出任何价格信息 |
| Web 菜单 | 评估模型 Jev（`category: evaluation`）在已配置时会出现在聊天模型下拉里，但服务端会以 `AGENT_MODEL_INVALID` 拒绝它 |

### 2.2 设计

**唯一费率来源**：`packages/billing/metering.py`

- `MODEL_RATES`：代码中经产品批准的费率（`(每次基础, 每千输入 token, 每千输出 token)`，单位 Credits）。`default` 表示平台默认路由（Agent 的 `default` 选择解析到的模型），**不是**未知模型的兜底。
- `AGENT_MODEL_CREDIT_RATES`（部署配置，`Settings.agent_model_credit_rates`）：格式 `id=基础/每千输入/每千输出`，逗号分隔，覆盖或补充 `MODEL_RATES`。解析严格：格式错误、负数、NaN/Inf 的条目直接丢弃——**丢弃 = 未定价 = 拒绝**，绝不猜价格。
- `explicit_model_rate(id, extra)`：返回某个可选模型的显式费率，没有则返回 `None`。
- `quote_credits(..., strict_model_rate=True, model_rates=...)`：用户选择了非 `default` 模型时启用。费率按**选择的 id**（`requested_model`）查找，报价、预留、结算三处一致；查不到时抛出 `ModelPricingNotConfigured`，不会回落到默认费率。
- `typical_turn_estimate(task_type, ...)`：用**同一个** `quote_credits` 计算“典型一轮”的区间：低档 `TYPICAL_TURN_LOW`（300 输入 / 500 输出 token，无付费数据源）与高档 `TYPICAL_TURN_HIGH`（2000 / 2000 token，读取 `market`、`rss` 两个付费数据源）。

**为什么没有直接用网关定价记录（`GatewayModel` / `GatewayPriceRevision` / `/gateway/catalog`）**：网关价格是美元/百万 token，而 Agent 计费单位是 Credits，仓库里**不存在**经批准的美元→Credits 换算。用网关价格推导 Credits 就等于发明一个换算率，所以没有这样做。网关目录只用于报告**能力**（见 2.3），价格仍以上述显式费率为准。将来若要以网关价格为准，需要先由产品确定换算策略，再在 `explicit_model_rate` 中接入。

**失败即拒绝（fail closed）**

| 入口 | 行为 |
| --- | --- |
| `_resolve_agent_model`（`quote_agent_run`、`start_run` 共用） | 在套餐和开关检查**之前**检查显式费率；没有则抛 `AgentModelPricingError("AGENT_MODEL_PRICING_NOT_CONFIGURED")`（继承 `AgentModelUnavailableError`，HTTP 503，路由层不需要新分支），不扣费、不创建 run |
| `POST /billing/quote` | 同样规则，返回 503 `AGENT_MODEL_PRICING_NOT_CONFIGURED` |
| 结算 `_settle_agent_run` | 按选择 id 计价；若运行中途费率被删除，按**预留金额**结算（预留本身来自显式费率），不会用其他模型的费率重新计价 |
| `agent_model_options` | 未定价模型：`available: false`，`reason: "pricing_not_configured"`，`estimate: null` |

原因优先级：`pricing_not_configured` > `plan_required` > `unavailable`。未定价的模型对任何套餐都不可用，提示“升级套餐”是误导。已定价模型的套餐门槛不变（`plan_required` 与原来一致）。

### 2.3 `GET /api/agent/capabilities` 中每个模型的字段

| 字段 | 含义 |
| --- | --- |
| `provider` | `openai` / 平台默认路由的实际 provider（取 `ModelRouter.route_for_task("agent_chat").provider_name`） |
| `capabilities` | `chat`，以及网关目录（`config/gateway/providers.yaml`）中该模型明确列出的 `reasoning` / `vision` / `tool_calling`。目录没有列出的模型**不报告**这些标志（表示未知，而不是 false） |
| `estimate` | `{min, max, unit: "credits", basis: "typical_turn", task_type}`，由 `typical_turn_estimate` 计算，与计费同源；未定价时为 `null` |
| `limits` | `plans`（允许的套餐，默认路由为 `null`）、`plan_allowed`、`image_input`（只有平台 DeepSeek 模型接受图片附件，与 `ATTACHMENT_IMAGE_MODEL_UNSUPPORTED` 规则一致） |
| `credit_cost` | 保留为 `null`，兼容旧客户端（模型没有固定单价） |

### 2.4 Web 菜单（`apps/web/components/agent-chat.tsx`，`#agent-model`）

- 只列出当前用户**现在能运行**的生成模型（`available && category !== "evaluation"`）；Jev 不再出现在聊天模型菜单里。
- 每个选项显示：名称 · provider（名称里已有则不重复）· 默认路由标记 · 服务端给出的典型一轮区间，例如 `DeepSeek V4.1 Flash · 平台默认路由 · 每轮约 2–6 Credits`、`GPT-5.6 Luna · OpenAI · ~6–12 Credits/turn`。
- 菜单下方说明不在列表中的模型及原因（按服务端 `reason` 分类计数：需要升级套餐 / 尚未配置计价 / 当前不可用）。
- 输入框下方的“预计 N Credits · 发送时预留 M”仍然只来自服务端 `/api/agent/quote`，没有改动。

### 2.5 启用 GPT-6 系列之前必须配置的内容

默认的 `gpt-6-luna`、`gpt-6-sol`、`gpt-6-astra` **在代码中没有费率**。本分支上线后，它们会在菜单中显示为“尚未配置计价”，报价和发送都会被拒绝。启用前需要：

1. 产品确认每个模型的 Credits 费率（基础 / 每千输入 / 每千输出）；
2. 在部署环境设置，例如（数值仅为格式示例，**不是**建议价格）：
   `AGENT_MODEL_CREDIT_RATES=gpt-6-luna=<基础>/<输入>/<输出>,gpt-6-sol=...,gpt-6-astra=...`
   或者把批准后的费率加入 `MODEL_RATES`；
3. 照旧满足 `OPENAI_LUNA_ENABLED=true`、`OPENAI_API_KEY` 和 `OPENAI_LUNA_ALLOWED_PLANS`；
4. 用 `GET /api/agent/capabilities` 确认对应模型 `available: true` 且 `estimate` 符合预期。

<!-- PART3 -->
