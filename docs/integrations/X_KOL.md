# X KOL
X KOL integration is a planned sentiment source for crypto market research. It should summarize public posts from selected accounts and never be treated as deterministic trading advice.
## Configuration
```text
X_API_KEY=
X_KOL_LIST=account1,account2,account3
```
## Current Status
`packages/data/x_provider.py` is a placeholder and returns neutral scores. The frontend data-source page marks X as requiring a key in fallback data.
## Planned Pipeline
1. Pull posts for allowed KOL accounts.
2. Deduplicate reposts and near-duplicate content.
3. Link posts to assets and narratives.
4. Score sentiment and topic intensity.
5. Rate-limit requests by provider policy.
6. Feed aggregate scores to shared market intelligence.
## Security and Privacy
- Treat KOL lists as internal strategy data.
- Do not log raw API credentials.
- Store source URL, account, timestamp, and processed score.
## Failure Modes
- API key missing.
- Rate limit exceeded.
- Account unavailable.
- Too much duplicate content.
- Sentiment spike from coordinated campaigns.
## Admin Response
If X rate limits block ingestion, mark source stale, reduce scan frequency, and avoid sending sentiment-driven claims without source freshness warnings.
