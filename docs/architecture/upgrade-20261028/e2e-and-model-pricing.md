# E2E 全量离线化与模型计价（2026-10-28）

状态：代码与测试已完成，**未执行任何生产部署、数据库迁移、切流或实盘开启**。
分支：`upgrade/e2e-and-model-pricing`。

本文分两部分：

- 第一部分：整套 Playwright 用例在离线环境（无真实 API）下全部通过，并在 CI 中全量运行；
- 第二部分：Agent 模型菜单与计价——每个可选模型都必须有显式费率，否则拒绝（fail closed）。

---

<!-- PART1 -->

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
