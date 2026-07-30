# PureGamma API Gateway

> An independent, prepaid OpenAI-compatible API for PureGamma users. Requests are routed only to enabled, reviewed official Provider APIs. PureGamma does not host local models and is not a model marketplace.

中文版：[PureGamma API 中转站](api-gateway.md)

## 1. Quick start

| Item | Value |
| --- | --- |
| API base URL | `https://api.puregamma.ai/v1` |
| Account and subscription | `https://app.puregamma.ai` |
| Available models | `GET /v1/models` |
| Chat API | `POST /v1/chat/completions` |

You need a verified PureGamma account, an API key beginning with `sk-pg-`, and sufficient **Gateway prepaid USD balance**. A user may keep up to ten active or paused keys. PureGamma Pro/Max/Enterprise subscriptions, plans, and Credits serve the PureGamma product only: they are **not** Gateway balance and do not determine whether a Gateway API request can run.

> **The model list is authoritative.** A model appears only after its Provider is enabled and healthy and its pricing has been approved. Do not treat a model name in an example as an availability guarantee.

Use the [PureGamma API Console](https://app.puregamma.ai/en/gateway) to create, pause, delete, or rotate keys and to view your monthly limit, model usage, and recent requests. A new key is displayed only at creation or rotation. Store it immediately in a password manager or secret manager, and never expose it in browser code, mobile apps, repositories, screenshots, or support tickets. Pause or rotate a key immediately if exposure is suspected.

### Add Gateway prepaid balance

In the API Console, enter any USD amount in **Add API balance** (currently **$5.00–$10,000.00**, configurable by the operator), then complete the one-time Stripe payment. Once the verified Stripe webhook receives the successful payment, the **exact payment amount is credited 1:1** to your Gateway USD balance and appears in wallet activity.

- This is not a subscription and never creates, upgrades, cancels, or changes a PureGamma plan.
- This is not a Credits purchase and never changes `credit_balance` or PureGamma feature quota.
- A balance is credited only after the verified Stripe webhook; the payment-success redirect itself never credits it.
- Gateway usage is charged only to this balance at approved retail pricing. Insufficient balance returns `402 GATEWAY_INSUFFICIENT_BALANCE`; the wallet never overdrafts.

### Gateway configuration card

Whether you use the OpenAI SDK, Dify, LangChain, Cursor, Continue, or your own backend, configure these values. Use **your own `sk-pg-...` key only**—never a DeepSeek, Kimi, or GLM provider key.

| Setting | Value |
| --- | --- |
| API type | OpenAI Compatible / OpenAI API |
| Base URL | `https://api.puregamma.ai/v1` |
| API key | `sk-pg-...` (kept in an environment variable) |
| Chat endpoint | `POST /chat/completions` (added automatically by an SDK) |
| Model | The exact `id` returned by `/v1/models` |

Suggested server-side `.env` values:

```bash
PUREGAMMA_API_KEY=sk-pg-...
PUREGAMMA_BASE_URL=https://api.puregamma.ai/v1
PUREGAMMA_MODEL=deepseek-v4-flash
```

Keep the `/v1` suffix in the Base URL. Do not use `https://app.puregamma.ai`, do not append `/chat/completions` to an SDK `base_url`, and never expose a key in browser code.

### Choose a model quickly

These are the Gateway's public model IDs and intended routing. A model appears in your `/v1/models` response only when its Provider is enabled and healthy and its official pricing has been approved. **Only call an ID actually returned by that endpoint.**

| Public model ID | Official Provider model | Good default for | Primary capabilities |
| --- | --- | --- | --- |
| `deepseek-v4-flash` | DeepSeek V4 Flash | Default selection, low-latency chat, and higher-volume tasks | Chat, streaming, JSON, tools, reasoning, cache |
| `deepseek-v4-pro` | DeepSeek V4 Pro | More complex analysis, code, and longer answers | Chat, streaming, JSON, tools, reasoning, cache |
| `kimi-k3-max` | Moonshot Kimi K3 | Long context and complex tool workflows | Chat, streaming, JSON, tools, reasoning, cache |
| `glm-5.2` | Zhipu GLM 5.2 | General Chinese/English tasks and tool calling | Chat, streaming, JSON, tools, cache |

Query the models once, then copy one returned `id` into your client configuration:

```bash
curl -sS https://api.puregamma.ai/v1/models \
  -H "Authorization: Bearer $PUREGAMMA_API_KEY"
```

The response uses the OpenAI model-list shape. In addition to `id`, `object`, `created`, and `owned_by`, PureGamma returns `display_name` and `capabilities`. Treat `capabilities` as the source of truth before enabling optional JSON, tools, or streaming behavior.

## 2. OpenAI SDK compatibility

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

for model in client.models.list().data:
    print(model.id)

completion = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "Explain compound interest in one sentence."}],
)
print(completion.choices[0].message.content)
```

```ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.PUREGAMMA_API_KEY,
  baseURL: "https://api.puregamma.ai/v1",
});

const completion = await client.chat.completions.create({
  model: "deepseek-v4-flash",
  messages: [{ role: "user", content: "Hello." }],
});
console.log(completion.choices[0].message.content);
```

```bash
curl -sS https://api.puregamma.ai/v1/models \
  -H "Authorization: Bearer $PUREGAMMA_API_KEY"
```

Minimal working request:

```bash
curl -sS https://api.puregamma.ai/v1/chat/completions \
  -H "Authorization: Bearer $PUREGAMMA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": "Introduce the PureGamma API in one sentence."}]
  }'
```

## 3. Chat, streaming, JSON, and tools

```http
POST /v1/chat/completions
Authorization: Bearer sk-pg-...
Content-Type: application/json
```

```json
{
  "model": "deepseek-v4-flash",
  "messages": [{"role": "user", "content": "Explain an ETF."}],
  "temperature": 0.2,
  "max_tokens": 300
}
```

Enabled chat models support ordinary responses, Server-Sent Event streaming, JSON mode, Tool Calling / Function Calling, and usage fields. Check each model's `capabilities` in `/v1/models` before relying on a feature.

```python
stream = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "Write a four-line poem."}],
    stream=True,
)
for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

Streams end with `data: [DONE]`. A stream is never moved to a different Provider after output begins, so clients should handle interrupted connections and retry according to their application semantics.

Tool definitions (`tools`, `tool_choice`) and legacy function fields are forwarded to the official Provider. Treat model-generated tool arguments as untrusted input: validate schemas, authorization, and idempotency before invoking any real system.

## 4. Usage, billing, and limits

Each request records its request ID, model, Provider, latency, input/output/cache/reasoning tokens, additional billable units, official cost, and retail cost. Retail pricing is calculated from an approved official price snapshot plus the active markup; the default markup is 30%.

Gateway accounts expose available prepaid balance, daily/monthly/lifetime spend, model-level usage, request history, API-key state, and an immutable wallet activity record. Each successful Gateway request is debited from the prepaid balance at the approved retail price. Insufficient funds return `402 GATEWAY_INSUFFICIENT_BALANCE`; reaching a configured monthly spend cap returns `402 GATEWAY_MONTHLY_LIMIT_REACHED`.

The Gateway can reuse the existing Stripe Customer for payment and receipts, but uses its own one-time `mode=payment` Checkout and its own ledger. It never reads or changes Subscription state, PureGamma Credits, or plan entitlement.

## 5. Error handling

| HTTP | Code | Recommended action |
| --- | --- | --- |
| 401 | `GATEWAY_INVALID_API_KEY` | Check the Bearer header; the key may be invalid, paused, or revoked. |
| 402 | `GATEWAY_INSUFFICIENT_BALANCE` | Add prepaid USD in the API Console through Stripe, then retry. |
| 402 | `GATEWAY_MONTHLY_LIMIT_REACHED` | A monthly limit was reached; contact the account administrator. |
| 403 | `GATEWAY_ACCOUNT_INACTIVE` | The Gateway account was suspended by an administrator; contact support. |
| 404 | `GATEWAY_MODEL_NOT_AVAILABLE` | Query `/v1/models`; the model may be disabled or awaiting price approval. |
| 429 | Rate limited | Reduce concurrency and retry with exponential backoff. |
| 503 | `GATEWAY_PROVIDER_UNHEALTHY` / `GATEWAY_PRICING_NOT_APPROVED` | Retry later or select an available model. |

Success and Gateway error responses include `X-Request-ID`. For support, supply that ID, UTC time, model ID, and HTTP status—never your API key, a full Authorization header, or sensitive prompt data.

## 6. Administrator operations

Administrator access is based on the PureGamma user record with `role=admin`; users cannot promote themselves. Administrators sign in through `https://app.puregamma.ai` with their own email or Google account and must use a protected management session. Never extract or share browser JWTs.

Use the [Gateway Admin Console](https://app.puregamma.ai/en/admin/gateway) for Provider enablement and health checks, catalog synchronization, pending-price approvals, unified markup, revenue/cost/profit metrics, and user spend caps or suspension. It is available only to accounts with `role=admin`; never share a browser session or token.

The management API responsibilities are: `/admin/gateway/providers` lists and enables Providers; `/admin/gateway/sync` synchronizes the catalog; `/admin/gateway/prices/pending` reviews price revisions; `/admin/gateway/prices/{revision_id}/approve` approves one; `/admin/gateway/pricing/markup` updates markup; `/admin/gateway/metrics` returns revenue, cost, profit, request count, and prepaid-balance liability; and `/admin/gateway/accounts` manages account state, monthly caps, and read-only API balance. The deployed customer console uses `/gateway/keys`, `/gateway/topups`, `/gateway/wallet`, `/gateway/dashboard`, and `/gateway/requests`.

### Gateway deployment configuration (administrators only)

The Gateway does not run models. Each provider key must come from that provider's official platform and belongs only in production `.env` or a secret manager. This is a field template: replace angle-bracket values securely and never commit them to Git.

```bash
GATEWAY_ENABLED=true
GATEWAY_API_KEY_PEPPER=<separate random secret, at least 32 characters>
GATEWAY_TOPUP_MIN_USD_CENTS=500
GATEWAY_TOPUP_MAX_USD_CENTS=1000000

GATEWAY_DEEPSEEK_API_KEY=<DeepSeek official key>
GATEWAY_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

GATEWAY_MOONSHOT_API_KEY=<Moonshot official key>
GATEWAY_MOONSHOT_BASE_URL=<Moonshot official endpoint matching account region>

GATEWAY_GLM_API_KEY=<Zhipu official key>
GATEWAY_GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
```

Keep the existing production `BILLING_MODE=stripe`, `STRIPE_SECRET_KEY`, and `STRIPE_WEBHOOK_SECRET` configuration. Configure the Stripe Endpoint to deliver `checkout.session.completed`, `checkout.session.async_payment_succeeded`, and `checkout.session.expired` to `POST https://api.puregamma.ai/stripe/webhook`. Never credit a wallet from a success URL, browser parameter, or an admin page: automated crediting must come from a signature-verified webhook whose amount, currency, Customer, and internal top-up intent all match.

After saving, restart API, worker, and scheduler. Then synchronize the catalog in the Admin Console, review every price, enable the Provider, run its health check, and verify `/v1/models` plus a low-cost call with a real `sk-pg-...` key. A provider key alone never bypasses price approval.

The operating sequence is: securely configure a Provider key; verify region, currency, and official pricing source; sync its catalog; review every pending price snapshot; explicitly approve the snapshot; health-check the Provider; then test `/v1/models` and a low-cost request with a real customer key. The scheduler performs a metadata sync daily at 03:00 Asia/Shanghai.

Adding a model never means adding an `if provider == ...` branch to the Router. Add or update an isolated Provider plugin and the official metadata in `config/gateway/providers.yaml`, then sync, review, approve, and test it. Publish only models actually returned by `/v1/models`.

## 7. Security and support

- API keys are HMAC-hashed; plaintext keys are never stored or shown again.
- Provider keys belong only in production secret configuration—not frontend code, documentation, logs, or Git.
- Use connection/read timeouts and exponential backoff for 429 and retryable 5xx responses.
- Check the key-storage policy before entering a production key into an editor integration or shared workspace.

For support, provide a redacted report containing `X-Request-ID`, time, model, and error code.
