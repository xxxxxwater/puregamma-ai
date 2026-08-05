# Public Data Sources

## Provider contract

Public providers implement health and sync operations with one of: `HEALTHY`, `PARTIAL`, `NEED_KEY`, `NOT_CONNECTED`, `NOT_LICENSED`, `RATE_LIMITED`, `ERROR`, `DISABLED`, or `MOCK_DEMO`.

Every persisted record includes provider, source URL when applicable, source timestamp, fetch timestamp, and explicit mock/fallback flags. Production sync never writes mock records.

## RSS

Feeds are configured in `config/rss_sources.yaml`. Only HTTPS hosts from this server-side file are accepted. Responses have a size limit and timeout, redirects are rejected, and ETag/Last-Modified validators are retained by the running worker. The parser stores title, short sanitized summary, canonical URL, publication time, source, deterministic sentiment, related symbols, and a content hash. It does not store full articles.

RSS deduplicates by canonical URL, source/external ID, and content hash. One failed feed produces `PARTIAL`; all failed feeds produce `ERROR`.

## Binance

`BinanceProvider` uses market-data-only Spot endpoints: ping, server time, exchange info, 24h ticker, current price, klines, and depth. It never exposes or calls order endpoints. Normalized quote amounts use `Decimal`/database `Numeric` and keep base volume separate from quote volume.

Default spot pairs are BTCUSDT, ETHUSDT, SOLUSDT, and HYPEUSDT. An unavailable pair fails independently. Equity and preferred-equity symbols never enter this provider.

## DefiLlama Free

Free endpoints use no API key. The adapter normalizes protocols/chains TVL, stablecoin supply, DEX volume, fees, and yield APY. Large responses have a separate 30 MB cap and only the configured maximum number of normalized rows per endpoint is retained. `DEFILLAMA_PRO_KEY` is optional and its absence does not downgrade Free API health.

## EVM RPC and subgraphs

RPC URLs are server-side environment variables. Allowed methods are limited to chain ID, latest block, block lookup, native balance, and allowlisted `eth_call` selectors for ERC-20 read methods. Address validation is mandatory. There are no send, sign, transaction, trace, or historical-transfer scan methods.

The subgraph registry is in `config/subgraphs.yaml`. Queries are selected from a static allowlist; clients and models cannot submit GraphQL. Entries remain disabled until a reviewed deployed endpoint is configured.

## Operations

Admin endpoints:

- `GET /admin/data-sources`
- `POST /admin/data-sources/{providerId}/sync`
- `POST /admin/data-sources/sync-all`
- `GET /admin/data-sources/{providerId}/runs`
- `GET /admin/data-sources/rss`
- `POST /admin/data-sources/rss/sync`

Celery/APScheduler jobs reuse the existing worker and use sync-run idempotency keys plus a running lease to avoid duplicate provider work.
