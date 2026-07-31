# Data License Policy

PureGamma stores provenance and licensing metadata on every source, raw document, and normalized document. Technical availability does not grant redistribution rights.

## Rules

- RSS: retain links, metadata, and configured summaries according to each publisher's terms. Do not assume an RSS feed grants republication rights.
- FinTwit/X: use official APIs or explicitly authorized feeds only. Do not scrape logged-in pages, evade rate limits, or remove attribution. Apply X retention, deletion, and display requirements to production deployments.
- Bloomberg: production requires a customer-held commercial agreement and an authorized interface. Never scrape Bloomberg websites, bypass access controls, or expose licensed article bodies to users not covered by the agreement.
- Mock data: use only in development and automated tests. It must be labeled `MOCK` and cannot support a factual market claim.
- Secrets: keep credentials in environment variables or a secret manager. Tokens, cookies, and full authorization headers must never enter logs.

## Redistribution and retention

`redistribution_allowed=false` is the default. The admin preview is access-controlled and the Agent returns attribution and source links, not a republished corpus. `retention_policy` records the governing policy; `DATA_RETENTION_DAYS` is only a local upper bound and must be reduced when a provider contract is stricter.

Production operators are responsible for contract review, user entitlements, deletion requests, display requirements, and audit evidence. A provider must remain `LICENSE_REQUIRED` or `NEEDS_KEY` until those controls are configured.
