# Jev / TypeSafe System One — PureGamma API Gateway

Status: feature branch; **not production enabled**. This is a typed decision API, not OpenAI Chat Completions and not a trading execution capability.

## Routes and contract

- `GET https://api.puregamma.ai/v1/systemone/models` — approved System One model discovery, using an existing PureGamma Gateway API key.
- `POST https://api.puregamma.ai/v1/systemone` — one native TypeSafe `POST https://api.typesafe.ai/v1/systemone` with `model`, `state`, and named `questions`.
- The model is version-pinned as `jev-1.13.0`, not the auto-moving `jev-latest` alias; the response retains the provider's actual reported model version.
- Question types: `noul` (yes probability), `choice` (one of supplied keys), `score` (ordered-level score). The gateway preserves the typed answers and usage; no fake chat response is synthesized.
- `POST /v1/chat/completions` must not be used with Jev. There is no model-initiated trade/order tool.

## Pricing, USD per million tokens

| Charge | Official | PureGamma ×1.30 |
|---|---:|---:|
| Input | $0.042 | $0.0546 |
| Output | $0.00 | $0.00 |

Source: https://docs.typesafe.ai/models (checked 2026-09-19). There is **no undocumented cache discount** or other inferred SKU. These are catalog quotes; a review/approval workflow activates pricing. Price changes require new revision and approval; avoid secretly mutating an active revision. The separate **USD prepaid Gateway wallet** is charged from actual provider-returned `usage.input_tokens`, not PureGamma SaaS subscription Credits. Do not claim a successful call is free if the upstream usage is malformed/missing.

## Enablement (operator-controlled)

1. Rotate any API key that has been pasted into a chat; provision a new, dedicated key as a server-side secret named `GATEWAY_TYPESAFE_API_KEY`. Do not put it into this repository, GitHub workflow text, `.env.example`, browser JS, screenshots, or logs.
2. Enable the existing Gateway intentionally (`GATEWAY_ENABLED=true` with a production key pepper). Add `typesafe` to `GATEWAY_ENABLED_PROVIDERS` without deleting existing enabled providers.
3. Run the existing gateway catalog/metadata sync and verify the TypeSafe model's status and its source reference. Administrator must approve the exact official USD price revision with the usual 3000-basis-point markup. Do not enable model before the provider health and approval gates succeed.
4. Confirm API key, separate wallet balance, monthly cap, logs, rate limits and end-to-end response shape. Start with a single low-token manual canary.
5. If the upstream returns a timeout/network error, its billing/delivery outcome may be unknown: **do not blindly replay the paid call**. Failed requests are logged by stable error code without dumping user state, bearer credentials or upstream response bodies.

## Customer smoke test (run locally, after approval)

Set a **PureGamma Gateway key**, not your upstream TypeSafe credential, in your own terminal environment. This command is a template, not proof of a live test:

```bash
export PUREGAMMA_API_KEY='<YOUR_PUREGAMMA_GATEWAY_KEY>'
curl --fail-with-body --silent --show-error https://api.puregamma.ai/v1/systemone \
  -H "Authorization: Bearer ${PUREGAMMA_API_KEY}" \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "model": "jev-1.13.0",
  "state": "Please review my refund today.",
  "questions": {
    "urgent": {"type": "noul", "instructions": "Does the customer explicitly request urgent action?"}
  }
}
JSON
```

Expected successful response has `model`, `answers.urgent.type = noul`, `answers.urgent.noul` between 0 and 1, `usage.input_tokens`, `usage.output_tokens`, and PureGamma `billing.amount_usd`, derived from the approved price revision. This is a semantic judgment, **not** a factual guarantee or trade authorization. Do not put private market/portfolio/account state into public logs.

## Test gates

`.github/workflows/jev-gateway.yml` runs offline HTTP-transport, malformed-usage, credential, API-auth, pricing and USD-wallet tests. No real TypeSafe key is passed into CI. A CI pass does not replace a deliberately approved live canary or prove production deployment. The broader Harness/Cordis migration and legacy retirement remain separate gates; do not merge an incomplete feature just because this subset passes.
