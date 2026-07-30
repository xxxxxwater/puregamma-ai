# PureGamma API Gateway

> An OpenAI-compatible API for paid PureGamma users. Requests are routed only to enabled, reviewed official Provider APIs. PureGamma does not host local models and is not a model marketplace.

中文版：[PureGamma API 中转站](api-gateway.md)

## 1. Quick start

| Item | Value |
| --- | --- |
| API base URL | `https://api.puregamma.ai/v1` |
| Account and subscription | `https://app.puregamma.ai` |
| Available models | `GET /v1/models` |
| Chat API | `POST /v1/chat/completions` |

You need a verified PureGamma account, an active Pro, Max, or Enterprise subscription, and an API key beginning with `sk-pg-`. A user may keep up to ten active or paused keys.

> **The model list is authoritative.** A model appears only after its Provider is enabled and healthy and its pricing has been approved. Do not treat a model name in an example as an availability guarantee.

The backend APIs for keys, usage, and request history are deployed; the customer self-service Gateway page is still being delivered. Until that page is available, use only a key issued through the verified PureGamma account-provisioning process. Store a new key immediately in a password manager or secret manager, and never expose it in browser code, mobile apps, repositories, screenshots, or support tickets. Pause or rotate a key immediately if exposure is suspected.

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

Gateway accounts expose daily, monthly, and lifetime spend; model-level usage; request history; and API-key state. Reaching a configured monthly spend limit returns `402 GATEWAY_MONTHLY_LIMIT_REACHED`.

Subscription eligibility uses the existing Stripe Customer, Subscription, and Webhook flows. This phase provides **usage metering, a cost ledger, and monthly-limit protection**. Before advertising usage-based collection, prepaid balance, or automatic top-ups, the operator must configure and accept the corresponding Stripe billing and settlement implementation.

## 5. Error handling

| HTTP | Code | Recommended action |
| --- | --- | --- |
| 401 | `GATEWAY_INVALID_API_KEY` | Check the Bearer header; the key may be invalid, paused, or revoked. |
| 402 | `GATEWAY_MONTHLY_LIMIT_REACHED` | A monthly limit was reached; contact the account administrator. |
| 403 | `GATEWAY_PAID_PLAN_REQUIRED` / `GATEWAY_SUBSCRIPTION_INACTIVE` | Activate an eligible paid subscription. |
| 404 | `GATEWAY_MODEL_NOT_AVAILABLE` | Query `/v1/models`; the model may be disabled or awaiting price approval. |
| 429 | Rate limited | Reduce concurrency and retry with exponential backoff. |
| 503 | `GATEWAY_PROVIDER_UNHEALTHY` / `GATEWAY_PRICING_NOT_APPROVED` | Retry later or select an available model. |

Success and Gateway error responses include `X-Request-ID`. For support, supply that ID, UTC time, model ID, and HTTP status—never your API key, a full Authorization header, or sensitive prompt data.

## 6. Administrator operations

Administrator access is based on the PureGamma user record with `role=admin`; users cannot promote themselves. Administrators sign in through `https://app.puregamma.ai` with their own email or Google account and must use a protected management session. Never extract or share browser JWTs.

The first phase has protected Gateway administration APIs for Providers, syncs, pending pricing, markup, metrics, and IP blocks, but a complete graphical Gateway administration console is **not yet delivered**. Until that console is available, do not expose internal administration endpoints to customers or manage production through shared tokens.

The management API responsibilities are: `/admin/gateway/providers` lists and enables Providers; `/admin/gateway/sync` synchronizes the catalog; `/admin/gateway/prices/pending` reviews price revisions; `/admin/gateway/prices/{revision_id}/approve` approves one; `/admin/gateway/pricing/markup` updates markup; and `/admin/gateway/metrics` returns revenue, cost, profit, and request count. The future customer page uses `/gateway/keys`, `/gateway/dashboard`, and `/gateway/requests`.

The operating sequence is: securely configure a Provider key; verify region, currency, and official pricing source; sync its catalog; review every pending price snapshot; explicitly approve the snapshot; health-check the Provider; then test `/v1/models` and a low-cost request with a real customer key. The scheduler performs a metadata sync daily at 03:00 Asia/Shanghai.

Adding a model never means adding an `if provider == ...` branch to the Router. Add or update an isolated Provider plugin and the official metadata in `config/gateway/providers.yaml`, then sync, review, approve, and test it. Publish only models actually returned by `/v1/models`.

## 7. Security and support

- API keys are HMAC-hashed; plaintext keys are never stored or shown again.
- Provider keys belong only in production secret configuration—not frontend code, documentation, logs, or Git.
- Use connection/read timeouts and exponential backoff for 429 and retryable 5xx responses.
- Check the key-storage policy before entering a production key into an editor integration or shared workspace.

For support, provide a redacted report containing `X-Request-ID`, time, model, and error code.
