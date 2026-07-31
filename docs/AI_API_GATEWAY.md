# PureGamma API Gateway (phase 1)

The gateway is a small, first-party API surface for paid PureGamma users. It is
not an inference service, marketplace, or proxy for arbitrary upstream URLs:
each configured Provider plugin calls only its official API.

## Activation

1. Deploy the database migration (`python -m scripts.db_migrate upgrade` is
   already the API container entrypoint).
2. Set `GATEWAY_ENABLED=true`, a separate random
   `GATEWAY_API_KEY_PEPPER` of at least 32 characters, and an explicit
   `GATEWAY_ENABLED_PROVIDERS` allow-list. Every listed provider needs its
   official API key and a matching regional pricing catalog. A staged launch
   may begin with `GATEWAY_ENABLED_PROVIDERS=deepseek`.
3. Deploy with `docker compose -f docker-compose.production.yml up -d --build`.
4. Sign in as an admin and call `POST /admin/gateway/bootstrap`, then
   `POST /admin/gateway/sync`.
5. Review the snapshots at `GET /admin/gateway/prices/pending` and approve each
   with `POST /admin/gateway/prices/{revision_id}/approve`.

Models remain unavailable until an administrator approves their first pricing
revision. This is intentional: an upstream catalog change cannot silently alter
customer billing.

## Official catalog status

The public `kimi-k3-max` identifier is retained for client compatibility, but
it is routed to Moonshot's official `kimi-k3` model id. The bundled catalog is
for Moonshot's global USD endpoint (`https://api.moonshot.ai/v1`) and must not
be combined with a China-region Moonshot credential or its CNY pricing.

The current catalog includes reviewed USD price snapshots for Kimi K3 and the
two DeepSeek V4 models, with links to their official price pages. GLM 5.2 is
kept pending: its published official rate is in CNY while the phase-1 ledger
and Stripe settlement are USD-denominated. An administrator must approve an
auditable CNY-to-USD conversion policy before adding a GLM billable price
snapshot. This avoids silently treating a CNY number as USD.

The existing Caddy edge proxy is retained instead of introducing a second
reverse proxy. This release does **not** treat `CF-Connecting-IP` as trusted:
the current Caddy configuration forwards the direct peer IP, which is a
Cloudflare edge address when the proxy is enabled. Before enabling the
gateway, restrict the Ubuntu origin's ports 80/443 to Cloudflare IP ranges
and configure Caddy's trusted-proxy handling so it forwards a verified
`CF-Connecting-IP` as `X-Real-IP`. Until then, do not use IP blocks or
IP-based anomaly decisions as a customer-identity control. Cloudflare
terminates at the public edge and Caddy obtains/renews the origin TLS
certificate.

## Pricing catalog

`config/gateway/providers.yaml` is data only. For each model, maintain the
official source reference and, when available, an `official_prices` object.
YAML accepts JSON as a subset, so an official JSON export can be used directly.
Prices are not hard-coded in Python. Each price SKU accepts an amount and unit:

```yaml
official_prices:
  input: { usd: "1.00", unit: per_million_tokens }
  output: { usd: "5.00", unit: per_million_tokens }
  cache: { usd: "0.50", unit: per_million_tokens }
  image: { usd: "0.10", unit: per_unit }
```

If a Provider exposes an official JSON pricing endpoint, configure its
`pricing_path` plus the optional `pricing_response_key`, `pricing_model_field`
and `pricing_field` metadata. The shared official-compatible plugin reads it
directly; providers without such an endpoint remain on the reviewed YAML/JSON
catalog path.

The same schema supports `reasoning`, `long_context`, `audio`, `search`,
`upload`, `download`, `batch`, and future SKU names. The default 30% markup is
stored as `3000` basis points; `PUT /admin/gateway/pricing/markup` immediately
creates approved replacement price snapshots from the same official data.

The scheduler syncs metadata at 03:00 Asia/Shanghai time and runs Provider
health checks every five minutes. A sync creates `pending_review` snapshots plus an auditable
`pricing_update_pending` event; it never activates a price automatically.

## Client API

Create a `sk-pg-…` key at `/gateway` (shown once) and use the standard OpenAI
SDK with a different base URL:

```python
from openai import OpenAI

client = OpenAI(api_key="sk-pg-…", base_url="https://api.puregamma.ai/v1")
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

Supported phase-1 model IDs are `kimi-k3-max`, `deepseek-v4-pro`,
`deepseek-v4-flash`, and `glm-5.2`. `POST /v1/chat/completions` supports
non-streaming and SSE streaming, JSON mode, tools/function calling, and usage
fields. `GET /v1/models` returns only approved, active models.

## Operational boundaries

- API keys are HMAC-hashed; raw key material is never stored or logged.
- A user can have at most 10 active or paused keys.
- Gateway access requires an active paid Stripe-backed plan; the existing
  Customer, Subscription and webhook flows are reused.
- Redis enforces per-key RPM limits and fails closed in production. IP blocks,
  request metadata, costs, errors, latency and token categories are retained in
  PostgreSQL; prompts and provider response bodies are not.
- Provider failover is configured by a model's database `routing.failover_models`
  list. The Router only invokes the plugin interface and contains no
  provider-specific branches. A stream is never moved after output has begun.
