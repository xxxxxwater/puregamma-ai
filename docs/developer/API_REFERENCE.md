# API Reference

Base URL for local development:

```text
http://localhost:8000
```

Protected endpoints require:

```text
Authorization: Bearer <token>
```

Investment outputs are research only and must include or preserve the disclaimer: `Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.`

## Auth

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/auth/mock-login` | No | `{"email":"demo@puregamma.ai","name":"Demo User"}` | `{"user":{"email":"demo@puregamma.ai","plan":"Free"},"access_token":"...","token_type":"bearer"}` | `400` validation | None | 0 |
| `GET` | `/me` | Yes | None | `{"user":{"id":"...","email":"...","role":"user","plan":"Free"}}` | `401` missing/invalid token | None | 0 |

## Market

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/health` | No | None | `{"status":"ok","service":"puregamma-api","billing_mode":"mock"}` | None expected | None | 0 |
| `GET` | `/assets` | No | None | `{"assets":[{"symbol":"BTC","name":"Bitcoin","category":"crypto","is_active":true}]}` | None expected | None | 0 |
| `GET` | `/market/snapshot` | No | None | `{"assets":[{"symbol":"BTC","price":108500,"funding_rate":0.006}]}` | None expected | None | 0 |
| `GET` | `/market/intelligence` | No | None | `{"id":"...","market_regime":"...","summary_markdown":"...","assets":["BTC"]}` | DB errors | None | 0 |
| `POST` | `/market/intelligence` | No | None | `{"id":"...","market_regime":"...","summary_markdown":"..."}` | DB errors | None | 0 |

## Reports

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/reports/daily` | Yes | None | `{"report":{"title":"PureGamma Daily Crypto Brief","report_type":"daily_market_report"}}` | `401`, `402` insufficient credits or limit | Action allowed for current plan | 10 unless cached |
| `POST` | `/reports/event` | Yes | `{"asset":"BTC","event":"ETF flow update"}` | `{"report":{"title":"PureGamma Event Report: BTC","assets":["BTC"]}}` | `401`, `402` | Current implementation does not call entitlement check | 5 |
| `GET` | `/reports` | Yes | None | `{"reports":[{"id":"...","title":"..."}]}` | `401` | Own reports only | 0 |
| `GET` | `/reports/{report_id}` | Yes | None | `{"report":{"id":"...","content_markdown":"..."}}` | `401`, `404` | Own report only | 0 |

## Signals

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/signals/scan` | Yes | None | `{"signals":[{"asset":"BTC","direction":"long_watch","disclaimer":"Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."}]}` | `401`, `402` insufficient credits | Current implementation does not block by plan | 8 |
| `GET` | `/signals` | Yes | None | `{"signals":[{"asset":"BTC","risk_score":46}]}` | `401` | Authenticated user | 0 |

## Playbooks

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/playbooks/generate` | Yes | None | `{"report":{"report_type":"playbook"},"playbooks":[{"strategy_name":"BTC momentum breakout"}]}` | `401`, `402` | High-cost task required | 30 |
| `GET` | `/playbooks` | Yes | None | `{"playbooks":[{"asset":"BTC"}],"reports":[]}` | `401` | Authenticated user | 0 |

## Portfolio

No backend portfolio endpoint is implemented yet. The web app uses frontend fallback data.

Planned endpoints:

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/portfolio/nav` | Yes | None | `{"nav":1284200,"partial_data":true,"positions":[]}` | `401`, `404` no portfolio | Pro or higher target | 0 |
| `POST` | `/portfolio/sync` | Yes | `{"sources":["plaid","exchange","onchain"]}` | `{"status":"queued"}` | `401`, `402`, provider errors | Source-specific plan | Source-specific, TBD |

## Integrations

General integration backend endpoints are planned. Current notification integrations are available through `/notifications/send`.

Planned connector endpoints:

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/integrations/plaid/link-token` | Yes | None | `{"link_token":"link-..."}` | `401`, Plaid config errors | Pro target | 0 |
| `POST` | `/integrations/plaid/exchange-public-token` | Yes | `{"public_token":"public-..."}` | `{"status":"connected"}` | `401`, Plaid errors | Pro target | 0 |
| `DELETE` | `/integrations/plaid/items/{item_id}` | Yes | None | `{"status":"disconnected"}` | `401`, `404` | Owner only | 0 |
| `POST` | `/integrations/exchanges` | Yes | redacted read-only key payload | `{"status":"connected"}` | `401`, validation errors | Max target | 0 |
| `POST` | `/integrations/wallets` | Yes | `{"address":"0x...","chain":"ethereum"}` | `{"status":"connected"}` | `401`, validation errors | Max target | 0 |

## Billing

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/billing/subscription` | Yes | None | `{"plan":"Free","subscription_status":"inactive","credit_balance":30,"entitlement":{}}` | `401` | Own subscription | 0 |
| `GET` | `/billing/credits` | Yes | None | `{"credit_balance":30,"usage_history":[]}` | `401` | Own ledger | 0 |
| `POST` | `/billing/create-checkout-session` | Yes | `{"plan_name":"Pro"}` | `{"checkout_url":"...","mode":"mock","price_id":"price_mock_pro"}` | `400`, `401` | Supported plan | 0 |
| `POST` | `/billing/create-portal-session` | Yes | None | `{"portal_url":"...","mode":"mock"}` | `400`, `401` | Existing Stripe customer | 0 |
| `POST` | `/billing/mock-upgrade` | Yes | `{"plan_name":"Max"}` | `{"plan":"Max","credit_balance":10030}` | `400`, `401` | `BILLING_MODE=mock` only | Grants credits |

## Stripe Webhook

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/stripe/webhook` | No; Stripe signature required in Stripe mode | Stripe event payload | `{"processed":true,"duplicate":false,"event_type":"invoice.paid"}` | `400` invalid signature/payload, `500` missing webhook secret | Stripe only | May grant credits |

## Notifications

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/notifications/test` | Yes | None | `{"delivery":{"channel":"email","status":"sent"}}` | `401` | Email channel | 1 unless existing idempotency key |
| `POST` | `/notifications/send` | Yes | `{"channel":"email","message":"...","metadata":{"idempotency_key":"..."}}` | `{"delivery":{"status":"sent","provider_response":{}}}` | `401`, provider failure recorded as delivery | Channel must be in plan | email/slack/telegram 1, iMessage 3 |
| `GET` | `/notifications/deliveries` | Yes | None | `{"deliveries":[{"channel":"email","status":"sent"}]}` | `401` | Own deliveries | 0 |

## iMessage

iMessage is exposed through notifications, not a separate API router.

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/notifications/send` | Yes | `{"channel":"imessage","message":"...","metadata":{"idempotency_key":"..."}}` | `{"delivery":{"channel":"imessage","status":"sent"}}` | skipped: missing recipient, entitlement denied, too long, rate limit, insufficient credits | Max or Enterprise and not past due | 3 |
| `POST` | relay `/send` | HMAC headers | `{"recipient":"+1555...","message":"...","idempotency_key":"..."}` | `{"status":"sent","duplicate":false}` | `401` invalid HMAC, `400` long message, `unsupported_os` | API-to-relay only | N/A |

## Nautilus

The real NautilusTrader runtime is not implemented. Current backend uses mock `BacktestEngine`.

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/backtest` | Yes | `{"strategy_name":"BTC momentum breakout","asset":"BTC","params":{"lookback_days":30}}` | `{"backtest":{"result":{"metrics":{"sharpe":1.23},"disclaimer":"Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."}}}` | `401`, `402` | High-cost task required | 25 |
| `GET` | `/backtest/{run_id}` | Yes | None | `{"backtest":{"id":"...","strategy_name":"..."}}` | `401`, `404` | Own run only | 0 |

## Data Sources

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/admin/data-sources` | Yes, admin | None | `{"data_sources":[{"name":"mock","status":"active"}]}` | `401`, `403` | Admin only | 0 |

Frontend data source sync actions are currently fallback-only and do not call backend routes.

## Admin

| Method | Path | Auth required | Request body | Response example | Errors | Entitlement | Credit cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/admin/users` | Yes, admin | None | `{"users":[{"email":"demo@puregamma.ai","role":"admin"}]}` | `401`, `403` | Admin only | 0 |
| `GET` | `/admin/reports` | Yes, admin | None | `{"reports":[{"title":"PureGamma Daily Crypto Brief"}]}` | `401`, `403` | Admin only | 0 |
| `GET` | `/admin/data-sources` | Yes, admin | None | `{"data_sources":[{"name":"binance","status":"adapter_ready"}]}` | `401`, `403` | Admin only | 0 |
| `GET` | `/admin/stripe-events` | Yes, admin | None | `{"stripe_events":[{"event_type":"invoice.paid","processed":true}]}` | `401`, `403` | Admin only | 0 |
| `GET` | `/admin/notifications` | Yes, admin | None | `{"notifications":[{"channel":"email","status":"sent"}]}` | `401`, `403` | Admin only | 0 |
| `GET` | `/admin/subscriptions` | Yes, admin | None | `{"subscriptions":[{"plan_name":"Pro","status":"active"}]}` | `401`, `403` | Admin only | 0 |

## Error Conventions

- `401`: missing or invalid bearer token.
- `403`: admin role required.
- `400`: invalid request or provider payload.
- `402`: insufficient credits or entitlement denied.
- `404`: resource not found or not owned by user.
