# CoinDesk RSS

CoinDesk RSS is a planned news input for market context and daily brief generation.

News-derived research is not financial advice and must not be represented as a recommendation.

## Configuration

```text
COINDESK_RSS_URL=https://www.coindesk.com/arc/outboundfeeds/rss/
```

## Current Status

`packages/data/rss_provider.py` returns placeholder headlines. Production ingestion should replace this with a real RSS fetcher, parser, deduplicator, and entity linker.

## Pipeline

1. Fetch RSS feed.
2. Parse title, link, published time, and summary.
3. Deduplicate by canonical URL and title hash.
4. Link assets and entities.
5. Score relevance and freshness.
6. Feed shared market intelligence.

## Safety

- Preserve source URL and timestamp.
- Do not quote full articles.
- Do not treat headlines as verified market truth.
- Show source freshness in reports.

## Troubleshooting

- Empty feed: check RSS URL and network.
- Duplicate headlines: improve canonical URL hashing.
- Wrong asset linking: update entity mapping.
