# PureGamma API 中转站

> 面向 PureGamma 用户的独立预付 OpenAI 兼容 API。所有请求只会转发至已审核、已启用的官方 Provider；PureGamma 不运行本地模型，也不是模型市场。

English version: [PureGamma API Gateway](api-gateway-en.md)

## 1. 开始使用

### 服务地址

| 项目 | 地址 |
| --- | --- |
| API Base URL | `https://api.puregamma.ai/v1` |
| 用户账户与订阅 | `https://app.puregamma.ai` |
| 可用模型 | `GET /v1/models` |
| 对话接口 | `POST /v1/chat/completions` |

访问条件：拥有已验证的 PureGamma 账户、一个 `sk-pg-...` API Key，以及足够的 **Gateway 预付 USD 余额**。每个用户最多可保留 10 个处于 active 或 paused 状态的 Key。PureGamma 的 Pro/Max/Enterprise 订阅、套餐与 Credits 只服务 PureGamma 产品，**不会**作为 Gateway 余额，也不会决定 Gateway API 是否可调用。

> **以模型列表为准。** 模型只有在 Provider 已启用、健康检查通过且价格已获管理员确认后才会出现在 `GET /v1/models`。请不要把文档或演示中出现的模型名称当作可用性承诺。

### 创建与保护 API Key

登录 [PureGamma API 控制台](https://app.puregamma.ai/zh/gateway) 后创建、暂停、删除或轮换 Key，并查看月度限额、模型用量和最近请求。新 Key 仅在创建或轮换时显示一次；请立即存入密码管理器或部署平台的密钥库。

不要把 Key 放入前端代码、移动应用、浏览器扩展、Git 仓库、截图或工单。怀疑泄露时请立刻暂停或轮换 Key；轮换会生成新 Key 并使旧 Key 失效。

### 充值 Gateway 预付余额

在 API 控制台的“充值 API 余额”中输入任意美元金额（当前范围为 **$5.00–$10,000.00**，可由运营方配置），然后前往 Stripe 完成一次性付款。Stripe 已验证的 Webhook 收到成功付款后，**付款金额 1:1 计入 Gateway USD 余额**，并显示在余额记录中。

- 这不是订阅，不会创建、升级、取消或变更 PureGamma 套餐。
- 这不是 Credits 充值，不会改变 `credit_balance` 或 PureGamma 功能额度。
- 余额只在已验证的 Stripe Webhook 回调后生效；支付成功跳转页本身不会入账。
- Gateway 调用仅从此余额按已确认的最终价格扣费。余额不足时 API 返回 `402 GATEWAY_INSUFFICIENT_BALANCE`，不会透支。

### 中转站配置卡（复制填写）

无论使用 OpenAI SDK、Dify、LangChain、Cursor、Continue，还是自己的后端服务，均填写以下四项；**不要使用 DeepSeek、Kimi 或 GLM 的官方 Key**，只能使用您自己的 `sk-pg-...` Key。

| 配置项 | 值 |
| --- | --- |
| API 类型 | OpenAI Compatible / OpenAI API |
| Base URL | `https://api.puregamma.ai/v1` |
| API Key | `sk-pg-...`（保存在环境变量中） |
| Chat endpoint | `POST /chat/completions`（SDK 会自动补全） |
| 模型 | `/v1/models` 返回的精确 `id` |

建议在服务端 `.env` 中保存：

```bash
PUREGAMMA_API_KEY=sk-pg-...
PUREGAMMA_BASE_URL=https://api.puregamma.ai/v1
PUREGAMMA_MODEL=deepseek-v4-flash
```

`Base URL` 必须保留结尾的 `/v1`。不要写成 `https://app.puregamma.ai`、不要把 `/chat/completions` 拼进 SDK 的 `base_url`，也不要在浏览器端暴露 Key。

### 模型快速选择

下面是 Gateway 的公共模型 ID 与路由设计。它们只有在 Provider 启用、健康检查通过、官方价格获管理员确认后才会出现在您的 `/v1/models` 返回中；**请求只可使用实际返回的 ID**。

| 公共模型 ID | 官方 Provider 模型 | 适合场景 | 主要能力 |
| --- | --- | --- | --- |
| `deepseek-v4-flash` | DeepSeek V4 Flash | 默认选项、低延迟对话与批量任务 | Chat、流式、JSON、工具、推理、缓存 |
| `deepseek-v4-pro` | DeepSeek V4 Pro | 更复杂的分析、代码与长回答 | Chat、流式、JSON、工具、推理、缓存 |
| `kimi-k3-max` | Moonshot Kimi K3 | 长上下文和复杂工具工作流 | Chat、流式、JSON、工具、推理、缓存 |
| `glm-5.2` | Zhipu GLM 5.2 | 通用中文/英文任务和工具调用 | Chat、流式、JSON、工具、缓存 |

先查询一次可用模型，再把其中一个 `id` 写入客户端配置：

```bash
curl -sS https://api.puregamma.ai/v1/models \
  -H "Authorization: Bearer $PUREGAMMA_API_KEY"
```

返回格式兼容 OpenAI 模型列表；除标准 `id`、`object`、`created`、`owned_by` 外，PureGamma 还会提供 `display_name` 与 `capabilities`。`capabilities` 是客户端是否启用 JSON、工具调用或流式等可选功能的唯一依据。

## 2. 五分钟接入

安装官方 OpenAI Python SDK：

```bash
pip install openai
```

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["PUREGAMMA_API_KEY"],
    base_url="https://api.puregamma.ai/v1",
)

# 始终先查询您自己的可用模型列表。
for model in client.models.list().data:
    print(model.id)

response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "用一句话解释复利。"}],
)
print(response.choices[0].message.content)
```

Node.js：

```bash
npm install openai
```

```ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.PUREGAMMA_API_KEY,
  baseURL: "https://api.puregamma.ai/v1",
});

const result = await client.chat.completions.create({
  model: "deepseek-v4-flash",
  messages: [{ role: "user", content: "Hello." }],
});
console.log(result.choices[0].message.content);
```

或使用 curl：

```bash
curl -sS https://api.puregamma.ai/v1/models \
  -H "Authorization: Bearer $PUREGAMMA_API_KEY"
```

最小可用请求：

```bash
curl -sS https://api.puregamma.ai/v1/chat/completions \
  -H "Authorization: Bearer $PUREGAMMA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍 PureGamma API。"}]
  }'
```

## 3. Chat Completions

接口遵循 OpenAI Chat Completions 结构：

```http
POST /v1/chat/completions
Authorization: Bearer sk-pg-...
Content-Type: application/json
```

```json
{
  "model": "deepseek-v4-flash",
  "messages": [
    {"role": "system", "content": "You are concise."},
    {"role": "user", "content": "Explain an ETF."}
  ],
  "temperature": 0.2,
  "max_tokens": 300
}
```

已启用的聊天模型支持普通响应、SSE 流式响应、JSON mode、Tool Calling / Function Calling 和 usage 字段。功能是否可用仍取决于模型在 `/v1/models` 返回的 `capabilities`。

### 流式响应

```python
stream = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "写一首四行短诗。"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content if chunk.choices else None
    if delta:
        print(delta, end="", flush=True)
```

流式接口使用 Server-Sent Events，并以 `data: [DONE]` 结束。流已开始输出后不会切换到其他 Provider，因此客户端应处理网络中断并按业务需要重新发起请求。

### JSON 与工具调用

```python
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": "给出一个 JSON 格式的待办事项。"}],
    response_format={"type": "json_object"},
)
```

工具定义、`tools`、`tool_choice`、旧版 `functions` 与 `function_call` 会转发到官方 Provider。请只把模型返回的工具参数当作**未验证输入**：在调用数据库、支付、交易、网络或文件系统前，必须自行做 schema 校验、权限检查和幂等处理。

## 4. 用量、费用与限额

每次请求都会记录请求 ID、模型、Provider、延迟、输入/输出/缓存/推理 Token、扩展计费单位、官方成本和最终成本。最终价格由已审核的官方价格和当前 markup 计算；默认 markup 为 30%。

用户可在 Gateway 用量页查看：可用预付余额、今日/本月/累计消费、按模型统计、请求历史、Key 最近使用状态，以及不可修改的余额记录。每笔成功 API 调用会从 Gateway 预付余额扣除最终价格；余额不足会返回 `402 GATEWAY_INSUFFICIENT_BALANCE`。当前月度消费上限到达后，接口会返回 `402 GATEWAY_MONTHLY_LIMIT_REACHED`。

Gateway 预付余额与现有 Stripe Customer 复用以方便支付和收据，但它使用独立的一次性 `mode=payment` Checkout 和独立账本；它不读取或修改 Subscription、PureGamma Credits 或套餐权益。

## 5. 常见错误

| HTTP | 代码 | 含义与处理 |
| --- | --- | --- |
| 401 | `GATEWAY_INVALID_API_KEY` | Key 缺失、错误、已撤销或已暂停；检查 `Authorization: Bearer ...`。 |
| 402 | `GATEWAY_INSUFFICIENT_BALANCE` | Gateway 预付余额不足；在 API 控制台使用 Stripe 充值后重试。 |
| 402 | `GATEWAY_MONTHLY_LIMIT_REACHED` | 已达到 Gateway 月度限额；联系账户管理员调整。 |
| 403 | `GATEWAY_ACCOUNT_INACTIVE` | Gateway 账户被管理员暂停；联系管理员。 |
| 404 | `GATEWAY_MODEL_NOT_AVAILABLE` | 模型未启用、未批准定价，或模型 ID 错误；先查询 `/v1/models`。 |
| 429 | Rate limited | 已超过该 Key 的 RPM；降低并发并使用退避重试。 |
| 503 | `GATEWAY_PROVIDER_UNHEALTHY` / `GATEWAY_PRICING_NOT_APPROVED` | 上游不可用或价格仍在审核；稍后重试或选择可用模型。 |

所有成功响应和 Gateway 错误响应均包含 `X-Request-ID`。向支持团队报障时，请提供该 ID、UTC 时间、模型 ID 与 HTTP 状态；不要发送 API Key、提示词中的私人数据或完整 Authorization Header。

## 6. 管理员运营说明

管理员资格由 PureGamma 用户记录的 `role=admin` 控制，用户不能自行提升权限。管理员应先以自己的邮箱或 Google 账户登录 `app.puregamma.ai`，并使用受保护的管理会话；不要从浏览器开发者工具复制或分发 JWT。

管理员可使用 [Gateway 管理台](https://app.puregamma.ai/zh/admin/gateway)。它提供 Provider 启停和健康检查、目录同步、待审价格确认、统一 markup、收入/成本/利润指标，以及用户月度消费上限和暂停/恢复。只有 `role=admin` 的账户可以访问；不要共享浏览器会话或 token。

管理 API 的职责如下：`/admin/gateway/providers` 查看与启停 Provider；`/admin/gateway/sync` 同步目录；`/admin/gateway/prices/pending` 审核价格；`/admin/gateway/prices/{revision_id}/approve` 确认价格；`/admin/gateway/pricing/markup` 调整 markup；`/admin/gateway/metrics` 查看收入、成本、利润、请求数和用户预付余额负债；`/admin/gateway/accounts` 管理用户 Gateway 状态、月度限额及只读 API 余额。用户侧 Key、充值、余额账本、用量和请求记录由 `/gateway/keys`、`/gateway/topups`、`/gateway/wallet`、`/gateway/dashboard`、`/gateway/requests` 提供给已上线的自助页面。

### 中转站部署配置（仅管理员）

Gateway 不运行模型；每个 Provider Key 必须来自相应官方平台，并且只能写入生产环境的 `.env` 或密钥管理服务。以下是字段模板，尖括号内容必须由管理员替换，绝不能提交到 Git：

```bash
GATEWAY_ENABLED=true
GATEWAY_API_KEY_PEPPER=<至少32字符的独立随机密钥>
GATEWAY_TOPUP_MIN_USD_CENTS=500
GATEWAY_TOPUP_MAX_USD_CENTS=1000000

GATEWAY_DEEPSEEK_API_KEY=<DeepSeek官方Key>
GATEWAY_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

GATEWAY_MOONSHOT_API_KEY=<Moonshot官方Key>
GATEWAY_MOONSHOT_BASE_URL=<与账户区域匹配的Moonshot官方端点>

GATEWAY_GLM_API_KEY=<Zhipu官方Key>
GATEWAY_GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
```

Stripe 必须保持现有生产 `BILLING_MODE=stripe`、`STRIPE_SECRET_KEY` 和 `STRIPE_WEBHOOK_SECRET` 配置。Stripe Endpoint 应投递 `checkout.session.completed`、`checkout.session.async_payment_succeeded` 与 `checkout.session.expired` 到 `POST https://api.puregamma.ai/stripe/webhook`。不要通过成功跳转 URL、浏览器参数或管理员页面直接增加用户余额；所有自动入账必须来自已验证签名且与内部充值 intent 的金额、币种、Customer 相符的 Webhook。

保存后重启 API、worker 与 scheduler；随后在管理台同步目录、逐项审核价格、启用 Provider、运行健康检查，并用真实的 `sk-pg-...` Key 验证 `/v1/models` 和低成本请求。不能因为 `.env` 有 Key 就跳过价格确认。

管理员的标准变更流程：

1. 将 Provider 官方 Key 安全写入生产环境的密钥管理或 `.env`，并限制文件权限；绝不提交 Git。
2. 仅在 Provider 具有匹配区域、币种与官方价格来源时启用它。
3. 执行 Catalog 同步；每日 03:00（Asia/Shanghai）也会自动同步。
4. 审核待确认价格：官方来源、计费单位、币种、输入/输出/缓存等 SKU、markup 与最终价格。
5. 明确确认每一个价格版本后，模型才会对用户可见。
6. 执行 Provider 健康检查并以真实 API Key 调用 `/v1/models` 与一次低成本测试请求。
7. 监控收入、官方成本、毛利、错误率、延迟、异常 IP 与每个用户的消费。

新增模型不是在 Router 中加入 `if` 分支：应新增或更新独立 Provider 插件和 `config/gateway/providers.yaml` 的官方元数据，完成同步、审核和测试。当前阶段只应向客户公布 `/v1/models` 实际返回的模型。

## 7. 安全与支持

- API Key 仅以 HMAC hash 存储，平台不会再次显示原始 Key。
- Provider Key 只保存在生产密钥配置中，不能出现在前端、文档、日志或 Git。
- 客户端应设置连接与读取超时，并对 429、可重试的 5xx 使用指数退避。
- 不要将真实密钥填进 Cursor、Continue、Open WebUI 等会同步配置到云端或团队共享的环境，除非已确认其密钥存储策略。

需要支持时，请提供 `X-Request-ID`、时间、模型与错误代码；敏感信息请先脱敏。
