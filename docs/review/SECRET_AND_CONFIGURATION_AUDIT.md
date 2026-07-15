# Secret and configuration audit

Configuration is currently concentrated in `apps/api/config.py` and `.env.example`. Production validation already rejects weak JWT/session secrets, demo fallback, missing cookie domain, missing Stripe secrets, weak runtime secret and non-HTTPS URLs.

Required production values are now explicitly validated by `scripts/validate-production-env.py` for:

`DATABASE_URL`, `POSTGRES_PASSWORD`, `REDIS_URL`, `JWT_SECRET`, `SESSION_SECRET`, `ENCRYPTION_MASTER_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `NEXT_PUBLIC_API_URL`, `INTERNAL_RUNTIME_SECRET`.

Secrets must be supplied by the deployment secret store, never committed. Exchange/OAuth tokens must use authenticated encryption before Portfolio connectors are enabled; the current Portfolio token field is a legacy compatibility path and requires a key.

