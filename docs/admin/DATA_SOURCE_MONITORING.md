# Data Source Monitoring

Data source monitoring tracks provider health, freshness, ingestion volume, and source-specific failures.

## Current Admin Endpoint

```text
GET /admin/data-sources
```

Current statuses are static or placeholder:

- `mock`: active.
- `binance`, `coingecko`, `defillama`: adapter ready.
- `x`, `glassnode`, `coinglass`: requires API key.

Frontend data-source rows use fallback data.

## Production Metrics To Add

- Last successful sync time.
- Last failed sync time.
- Failure reason.
- Items ingested.
- Provider latency.
- Rate-limit remaining.
- Source freshness SLA.
- Partial-data impact.

## Monitoring Rules

- Reports should show stale-source warnings.
- Portfolio NAV should show `partial_data=true` when source data is missing.
- KOL or news-driven conclusions should not be sent when source freshness is stale.

## Admin Actions

- Disable source if provider returns invalid data.
- Lower sync frequency when rate limited.
- Re-run sync for one source.
- Mark a source as degraded.
- Escalate licensing or credential failures.
