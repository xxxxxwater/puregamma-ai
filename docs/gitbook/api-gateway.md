# PureGamma API 中转站

> 面向 PureGamma 付费用户的 OpenAI 兼容 API。所有请求只会转发至已审核、已启用的官方 Provider；PureGamma 不运行本地模型，也不是模型市场。

English version: [PureGamma API Gateway](api-gateway-en.md)

## 1. 开始使用

### 服务地址

| 项目 | 地址 |
| --- | --- |
| API Base URL | `https://api.puregamma.ai/v1` |
| 用户账户与订阅 | `https://app.puregamma.ai` |
| 可用模型 | `GET /v1/models` |
| 对话接口 | `POST /v1/chat/completions` |

访问条件：拥有已验证的 PureGamma 账户、处于有效状态的 Pro、Max 或 Enterprise 订阅，以及一个 `sk-pg-...` API Key。每个用户最多可保留 10 个处于 active 或 paused 状态的 Key。

> **以模型列表为准。** 模型只有在 Provider 已启用、健康检查通过且价格已获管理员确认后才会出现在 `GET /v1/models`。请不要把文档或演示中出现的模型名称当作可用性承诺。

### 创建与保护 API Key

Gateway 的 Key、用量与请求历史后端接口已经部署；面向客户的自助 Gateway 页面仍在交付中。在该页面上线前，只有通过 PureGamma 已验证的账户开通流程取得的 Key 才能使用。新 Key 仅在创建或轮换时显示一次；请立即存入密码管理器或部署平台的密钥库。

不要把 Key 放入前端代码、移动应用、浏览器扩展、Git 仓库、截图或工单。怀疑泄露时请立刻暂停或轮换 Key；轮换会生成新 Key 并使旧 Key 失效。

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

用户可在 Gateway 用量页查看：今日、本月、累计消费；按模型统计；请求历史；Key 最近使用时间和状态。当前月度消费上限到达后，接口会返回 `402 GATEWAY_MONTHLY_LIMIT_REACHED`。

订阅资格由现有 Stripe Customer、Subscription 与 Webhook 流程决定。Gateway 目前提供**用量计量、成本账本与月度限额保护**；在对外公布按量扣费、预付余额或自动充值前，运营方必须先配置并验收对应的 Stripe 计费产品与结算流程。

## 5. 常见错误

| HTTP | 代码 | 含义与处理 |
| --- | --- | --- |
| 401 | `GATEWAY_INVALID_API_KEY` | Key 缺失、错误、已撤销或已暂停；检查 `Authorization: Bearer ...`。 |
| 402 | `GATEWAY_MONTHLY_LIMIT_REACHED` | 已达到 Gateway 月度限额；联系账户管理员调整。 |
| 403 | `GATEWAY_PAID_PLAN_REQUIRED` / `GATEWAY_SUBSCRIPTION_INACTIVE` | 需要有效的付费订阅。 |
| 404 | `GATEWAY_MODEL_NOT_AVAILABLE` | 模型未启用、未批准定价，或模型 ID 错误；先查询 `/v1/models`。 |
| 429 | Rate limited | 已超过该 Key 的 RPM；降低并发并使用退避重试。 |
| 503 | `GATEWAY_PROVIDER_UNHEALTHY` / `GATEWAY_PRICING_NOT_APPROVED` | 上游不可用或价格仍在审核；稍后重试或选择可用模型。 |

所有成功响应和 Gateway 错误响应均包含 `X-Request-ID`。向支持团队报障时，请提供该 ID、UTC 时间、模型 ID 与 HTTP 状态；不要发送 API Key、提示词中的私人数据或完整 Authorization Header。

## 6. 管理员运营说明

管理员资格由 PureGamma 用户记录的 `role=admin` 控制，用户不能自行提升权限。管理员应先以自己的邮箱或 Google 账户登录 `app.puregamma.ai`，并使用受保护的管理会话；不要从浏览器开发者工具复制或分发 JWT。

当前第一阶段已部署受权限保护的 Gateway 管理 API（Provider、同步、待审价格、markup、运营指标与 IP Block），但**完整的图形化 Gateway 管理台尚未交付**。在管理台上线前，不应让普通用户使用内部管理接口，也不应通过共享 token 管理生产环境。

管理 API 的职责如下：`/admin/gateway/providers` 查看与启停 Provider；`/admin/gateway/sync` 同步目录；`/admin/gateway/prices/pending` 审核价格；`/admin/gateway/prices/{revision_id}/approve` 确认价格；`/admin/gateway/pricing/markup` 调整 markup；`/admin/gateway/metrics` 查看收入、成本、利润与请求数。用户侧 Key、用量和请求记录分别由 `/gateway/keys`、`/gateway/dashboard`、`/gateway/requests` 提供给未来的自助页面。

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
