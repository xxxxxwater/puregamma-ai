# Data Sources

PureGamma's primary research-document pipeline supports RSS, FinTwit, the official X API, and authorized Bloomberg connections. Legacy market and on-chain adapters remain extension providers but are not part of this pipeline's scheduler.

## Common contract

Every provider implements `DataProvider` in `packages/data/provider.py`: health, latest/cursor fetch, normalization, deduplication, usage, and status. Documents are stored in this order:

`Source -> RawDocument -> NormalizedDocument -> EntityMention/SentimentSignal`

All timestamps are UTC. The normalized record retains provider, original URL, author, publication time, license state, retention policy, engagement, symbols, topics, sentiment, and the raw payload reference.

## RSS

Feeds are configured in `config/rss_sources.yaml`; URLs are not embedded in business services. Each feed can set credibility, language, license, redistribution, and retention metadata. The provider sends `If-None-Match` and `If-Modified-Since`, retries transient failures with exponential backoff, canonicalizes URLs, sanitizes markup, and derives stable hashes.

Set `RSS_SYNC_INTERVAL`, `RSS_REQUEST_TIMEOUT`, and `RSS_CONFIG_PATH`. The admin can sync, pause, resume, check configuration, and inspect recent records.

## FinTwit

FinTwit is a curated opinion stream, not a newswire. Accounts are seeded from `config/fintwit_accounts.yaml` into `fintwit_accounts`, then maintained in the admin API. Only enabled whitelist accounts are accepted. Each account has a category, credibility, weight, optional historical accuracy, provider user ID, and collection method.

The current production method is `official_api`, backed by X user timelines. Set each account's official X user ID and `X_BEARER_TOKEN`. The service does not scrape X pages or bypass platform controls.

## X / Twitter

The adapter uses X API v2 recent search, list posts, and user timelines. It supports `pagination_token`, records rate-limit headers, caps requests per sync, and persists the next cursor. Missing credentials produce `NEEDS_KEY`, never `HEALTHY`.

Configure `X_BEARER_TOKEN`, optionally `X_SEARCH_QUERY`, `X_LIST_ID`, `X_REQUEST_BUDGET_PER_SYNC`, and `X_SYNC_INTERVAL`. Stored content remains subject to the X Developer Agreement and configured retention.

## Bloomberg

`BLOOMBERG_MODE=disabled` reports `LICENSE_REQUIRED`. `mock` is accepted only outside production and produces visibly marked, zero-credibility test metadata. `production` requires:

- `BLOOMBERG_LICENSE_STATUS=authorized|licensed|active`
- an HTTPS `BLOOMBERG_API_URL` supplied under the customer's agreement
- `BLOOMBERG_API_KEY`
- contract-specific retention and redistribution configuration

The generic authorized REST adapter is an integration boundary, not a Bloomberg web scraper. A BLPAPI/SAPI customer can replace its transport while preserving the provider contract. If the licensed response supplies metadata only, the adapter leaves article content empty.

## Operations

Provider failures are isolated. Three consecutive failures open a 15-minute circuit; a manual admin sync can probe recovery. Sync logs retain cursors, counts, duplicates, HTTP status, retries, quota, reset time, and redacted errors. The daily cleanup task enforces `DATA_RETENTION_DAYS`; stricter provider contracts take precedence.
