# Environment Variables

Copy `.env.example` to `.env` and fill only the values needed for your environment.

Do not put real secrets in documentation, tests, screenshots, or commits. Use a secret manager in production.

Sensitivity levels:

- Public: safe in frontend or logs.
- Internal: operational setting; avoid public exposure.
- Secret: credential or signing key; never log.
- Restricted: user or enterprise sensitive connector credential; encrypt if stored.

## Core

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `APP_ENV` | No | `development` | `production` | Use for deployment labeling and runtime policy. | Internal |
| `LOG_LEVEL` | No | `info` | `warning` | Avoid debug logging in production. | Internal |
| `JWT_SECRET` | Yes | `change-me` | `use-a-32-byte-random-value` | Must be high entropy and rotated through a planned session invalidation process. | Secret |
| `AUTH_ALLOW_DEMO_FALLBACK` | No | `false` | `false` | Keep false outside isolated demos. | Internal |
| `NEXT_PUBLIC_API_URL` | Web only | `http://localhost:8000` | `https://api.example.com` | Public browser value. | Public |
| `GOOGLE_CLIENT_ID` | Required for Google OAuth | empty | `...apps.googleusercontent.com` | Server-side OAuth client ID used for authorize URL and ID token audience check. | Internal |
| `GOOGLE_CLIENT_SECRET` | Required for Google OAuth | empty | `...` | Never expose to the frontend. | Secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | Required for Google OAuth | `http://127.0.0.1:8000/auth/google/callback` | `https://api.example.com/auth/google/callback` | Must exactly match the URI configured in Google Cloud and token exchange; the API sets the session cookie and redirects to `SITE_URL`. | Public |

## Database

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `DATABASE_URL` | Yes | `postgresql+psycopg://puregamma:puregamma@localhost:5432/puregamma` | `postgresql+psycopg://user:pass@db:5432/puregamma` | Use managed Postgres, TLS, backups, and least-privilege credentials. | Secret |

## Redis and Workers

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `REDIS_URL` | Yes for workers | `redis://localhost:6379/0` | `rediss://:pass@redis.example.com:6379/0` | Use TLS and auth in production. | Secret |
| `WORKER_CONCURRENCY` | No | `2` | `4` | Size based on queue latency and provider rate limits. | Internal |

## LLM

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `LLM_PROVIDER` | No | `mock` | `deepseek` | Use `mock`, `openai`, or `deepseek`. Missing real keys fall back to mock. | Internal |
| `OPENAI_API_KEY` | Required for real LLM | empty | `sk-...` | Store in secret manager and monitor usage. | Secret |
| `OPENAI_BASE_URL` | No | empty | `https://api.openai.com/v1` | Use only trusted OpenAI-compatible endpoints. | Internal |
| `OPENAI_MODEL` | No | empty | `gpt-4.1-mini` | Provider-specific override for OpenAI-compatible routing. | Internal |
| `OPENAI_TRANSCRIBE_MODEL` | No | `gpt-4o-mini-transcribe` | `gpt-4o-mini-transcribe` | Server-side speech-to-text model used by the optional Private Secretary voice input. | Internal |
| `NOIZ_API_KEY` | Required for Secretary voice output | empty | `...` | Store only in the server secret store; never expose it to the browser or commit it. | Secret |
| `NOIZ_VOICE_ID` | No | `183203aa0` | `183203aa0` | Default Chinese voice identifier. | Internal |
| `NOIZ_ENGLISH_VOICE_ID` | No | `7bc8b578` | `7bc8b578` | Default English voice identifier. | Internal |
| `LLM_MODEL` | No | empty | `gpt-4.1-mini` | Pin model per environment before production. | Internal |
| `DEEPSEEK_API_KEY` | Required when `LLM_PROVIDER=deepseek` | empty | `...` | Keep blank in examples and store real values only in secret manager or local `.env`. | Secret |
| `DEEPSEEK_BASE_URL` | No | `https://api.deepseek.com` | `https://api.deepseek.com` | OpenAI-compatible base URL. | Internal |
| `DEEPSEEK_MODEL` | No | `deepseek-v4-flash` | `deepseek-v4-flash` | Default DeepSeek model for research generation. | Internal |
| `DEEPSEEK_THINKING_MODE` | No | `disabled` | `disabled` | Reserved for provider-specific reasoning controls. | Internal |
| `DEEPSEEK_TIMEOUT_SECONDS` | No | `60` | `60` | Keep finite to protect worker latency. | Internal |

## Stripe

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `BILLING_MODE` | Yes | `mock` | `stripe` | Use `stripe` only after webhook signing and prices are configured. | Internal |
| `BILLING_CHECKOUT_MODE` | No | `session` | `payment_link` | Selects Checkout Sessions or Payment Links in the web billing page. | Internal |
| `STRIPE_SECRET_KEY` | Yes when Stripe mode | empty | `sk_test_...` | Use restricted keys where possible. | Secret |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | Web only | empty | `pk_test_...` | Public browser key. | Public |
| `STRIPE_WEBHOOK_SECRET` | Yes when Stripe mode | empty | `whsec_...` | Required for signature verification. | Secret |
| `STRIPE_WEBHOOK_TOLERANCE_SECONDS` | No | `300` | `300` | Reject old webhook signatures to reduce replay risk. | Internal |
| `STRIPE_API_VERSION` | No | `2026-02-25.clover` | `2026-02-25.clover` | Keep pinned and test before upgrades. | Internal |
| `STRIPE_PRICE_PRO` | Yes for Stripe checkout | empty | `price_...` | Must match recurring Price for Pro. | Internal |
| `STRIPE_PRICE_MAX` | Yes for Stripe checkout | empty | `price_...` | Must match recurring Price for Max. | Internal |
| `STRIPE_PRICE_ENTERPRISE` | Yes for Enterprise checkout | empty | `price_...` | Enterprise may also use manual invoicing. | Internal |
| `STRIPE_PAYMENT_LINK_PRIMARY` | Optional | configured demo link | `https://buy.stripe.com/...` | Shared fallback Payment Link; completed checkout requires webhook plan proof or manual review. | Internal |
| `STRIPE_PAYMENT_LINK_PRO` | Required for Pro Payment Link mode | empty | `https://buy.stripe.com/...` | Plan-specific Payment Link for Pro. | Internal |
| `STRIPE_PAYMENT_LINK_MAX` | Required for Max Payment Link mode | empty | `https://buy.stripe.com/...` | Plan-specific Payment Link for Max. | Internal |
| `STRIPE_PAYMENT_LINK_ENTERPRISE` | Required for Enterprise Payment Link mode | empty | `https://buy.stripe.com/...` | Plan-specific Payment Link for Enterprise. | Internal |
| `STRIPE_SUCCESS_URL` | Yes | `http://localhost:3000/billing/success` | `https://app.example.com/billing/success` | Must be on trusted app domain. | Public |
| `STRIPE_CANCEL_URL` | Yes | `http://localhost:3000/billing/cancel` | `https://app.example.com/billing/cancel` | Must be on trusted app domain. | Public |

## iMessage

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `IMESSAGE_PROVIDER` | Yes | `mock` | `macos_relay` | Use `mock` unless a secured Mac relay is deployed. | Internal |
| `IMESSAGE_RELAY_URL` | Yes for relay | `http://localhost:8787` | `https://relay.example.internal` | Restrict network access. | Internal |
| `IMESSAGE_RELAY_SECRET` | Yes for relay | empty | `random-hmac-secret` | Shared HMAC secret between API and relay. | Secret |
| `IMESSAGE_RELAY_DB` | No | `./imessage_relay.sqlite3` | `/var/lib/puregamma/relay.sqlite3` | Persist for idempotency audit. | Internal |
| `IMESSAGE_ENABLED_PLANS` | No | `Max,Enterprise` | `Max,Enterprise` | Must match entitlement policy. | Internal |
| `IMESSAGE_MAX_MESSAGE_LENGTH` | No | `3000` | `3000` | Keep below provider and UX limits. | Internal |
| `IMESSAGE_RATE_LIMIT_PER_USER_PER_DAY` | No | `20` | `20` | Lower for production launch if abuse risk is high. | Internal |
| `IMESSAGE_REPLAY_TOLERANCE_SECONDS` | No | `300` | `300` | HMAC replay window. | Internal |
| `IMESSAGE_APPLESCRIPT_PATH` | No | bundled script | `/opt/puregamma/send_imessage.applescript` | Lock file permissions. | Internal |

## Telegram

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Required for real Telegram | empty | `123456:ABC...` | Rotate if leaked. | Secret |

## Slack

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `SLACK_WEBHOOK_URL` | Required for shared Slack fallback | empty | `https://hooks.slack.com/services/...` | Prefer per-user webhook storage when implemented. | Secret |

## Email

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `SMTP_HOST` | Required for real email | empty | `smtp.sendgrid.net` | Use provider with bounce handling. | Internal |
| `SMTP_PORT` | No | `587` | `587` | TLS is started by the current provider. | Internal |
| `SMTP_USER` | Required for authenticated SMTP | empty | `apikey` | Do not log. | Secret |
| `SMTP_PASSWORD` | Required for authenticated SMTP | empty | `SG...` | Do not log. | Secret |

## Plaid

Plaid backend routes are planned. These variables define the expected contract.

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `PLAID_ENV` | Yes for Plaid | `sandbox` | `production` | Use `sandbox` for local and test. | Internal |
| `PLAID_CLIENT_ID` | Yes for Plaid | empty | `client-id` | Store in secret manager. | Secret |
| `PLAID_SECRET` | Yes for Plaid | empty | `secret` | Store in secret manager. | Secret |
| `PLAID_PRODUCTS` | No | `investments` | `investments` | PureGamma uses investments data only. | Internal |
| `PLAID_REDIRECT_URI` | Conditional | local callback | `https://app.example.com/integrations/plaid/callback` | Must match Plaid dashboard configuration. | Public |

## Exchange

Exchange sync is planned. All keys must be read-only.

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `EXCHANGE_KEY_ENCRYPTION_KEY` | Yes before storing keys | empty | `base64-32-byte-key` | Required for encrypted credential storage. | Secret |
| `BINANCE_API_KEY` | Optional | empty | `...` | Read-only only; never withdrawal or trade. | Restricted |
| `BINANCE_API_SECRET` | Optional | empty | `...` | Encrypt if persisted. | Restricted |
| `OKX_API_KEY` | Optional | empty | `...` | Read-only only. | Restricted |
| `OKX_API_SECRET` | Optional | empty | `...` | Encrypt if persisted. | Restricted |
| `OKX_API_PASSPHRASE` | Optional | empty | `...` | Encrypt if persisted. | Restricted |
| `BYBIT_API_KEY` | Optional | empty | `...` | Read-only only. | Restricted |
| `BYBIT_API_SECRET` | Optional | empty | `...` | Encrypt if persisted. | Restricted |
| `HYPERLIQUID_WALLET_ADDRESS` | Optional | empty | `0x...` | Public address is lower sensitivity, but still user data. | Restricted |

## On-chain

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `ONCHAIN_RPC_URL` | Optional | empty | `https://eth-mainnet.g.alchemy.com/v2/...` | Prefer provider-specific URLs. | Secret |
| `ETHEREUM_RPC_URL` | Optional | empty | `https://...` | Rate-limit and monitor. | Secret |
| `BASE_RPC_URL` | Optional | empty | `https://...` | Rate-limit and monitor. | Secret |
| `ARBITRUM_RPC_URL` | Optional | empty | `https://...` | Rate-limit and monitor. | Secret |
| `ALCHEMY_API_KEY` | Optional | empty | `...` | Do not expose in browser. | Secret |
| `PORTFOLIO_TOKEN_ENCRYPTION_KEY` | Required before token storage | empty | `base64-32-byte-key` | Use for Plaid and connector token encryption. | Secret |

## Data Providers

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `COINDESK_RSS_URL` | No | CoinDesk RSS URL | `https://www.coindesk.com/arc/outboundfeeds/rss/` | RSS does not require a secret. | Public |
| `COINGECKO_API_KEY` | Optional | empty | `CG-...` | Use for higher rate limits. | Secret |
| `DEFILLAMA_API_KEY` | Optional | empty | `...` | Only if paid API is used. | Secret |
| `X_API_KEY` | Required for real X scans | empty | `...` | Treat as high-risk API key. | Secret |
| `X_KOL_LIST` | Optional | empty | `account1,account2` | May reveal strategy sources. | Internal |
| `CRYPTOPANIC_API_KEY` | Optional | empty | `...` | Do not log. | Secret |
| `GLASSNODE_API_KEY` | Optional | empty | `...` | Do not log. | Secret |
| `COINGLASS_API_KEY` | Optional | empty | `...` | Do not log. | Secret |
| `FRED_API_KEY` | Optional | empty | `...` | Lower sensitivity, still keep server-side. | Secret |

## Bloomberg

Bloomberg import is planned for enterprise/private deployments.

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `BLOOMBERG_ENABLED` | No | `false` | `true` | Enable only in enterprise environments with licensed access. | Internal |
| `BLOOMBERG_DATA_DIR` | Conditional | empty | `/mnt/bloomberg/drop` | Secure file permissions. | Restricted |
| `BLOOMBERG_SFTP_HOST` | Conditional | empty | `sftp.example.com` | Use allowlists and key auth. | Internal |
| `BLOOMBERG_SFTP_USER` | Conditional | empty | `puregamma` | Least privilege. | Internal |
| `BLOOMBERG_SFTP_PRIVATE_KEY` | Conditional | empty | `/run/secrets/bbg_key` | Store as file secret, not inline. | Secret |

## NautilusTrader

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `NAUTILUS_ENABLED` | No | `false` | `true` | Current runtime is mock; real integration is planned. | Internal |
| `NAUTILUS_DATA_DIR` | No | `./data/nautilus` | `/var/lib/puregamma/nautilus` | Persist and back up research data if used. | Internal |
| `NAUTILUS_LIVE_TRADING_ENABLED` | Required safety flag | `false` | `false` | Must remain false for MVP. | Internal |
| `NAUTILUS_ALLOW_LIVE_ORDER` | Required safety flag | `false` | `false` | Must remain false unless an audited future release enables trading. | Internal |

## Security and Observability

| Variable | Required | Default | Example | Production notes | Sensitivity |
| --- | --- | --- | --- | --- | --- |
| `SENTRY_DSN` | Optional | empty | `https://...@sentry.io/...` | Scrub secrets and PII before sending events. | Secret |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Optional | empty | `https://otel.example.com` | Use TLS and auth. | Internal |
| `AUDIT_LOG_RETENTION_DAYS` | No | `365` | `365` | Align with enterprise contract and deletion policy. | Internal |
