# Agent controlled online research

Agent Chat queries synchronized PureGamma data first. When required source-document evidence is still missing, the runtime may perform one controlled public metadata search before asking the model to compose an answer.

## Production behavior

- `AGENT_ONLINE_RESEARCH_ENABLED=true` enables the fallback.
- `ONLINE_SEARCH_PROVIDER=google_news` uses the fixed Google News RSS search endpoint without an API key.
- `ONLINE_SEARCH_PROVIDER=brave` uses the fixed Brave Search API and requires `BRAVE_SEARCH_API_KEY`.
- `ONLINE_SEARCH_TIMEOUT_SECONDS=10`, `ONLINE_SEARCH_MAX_RESULTS=8`, and `ONLINE_SEARCH_MAX_RESPONSE_BYTES=1000000` bound cost and resource use.
- The tool is read-only, requires the user's existing `rss` entitlement, is metered, and is available only to reviewed Skills that include `search_online_sources`.

The runtime never fetches a result page and never follows redirects. User-supplied URLs are not opened. Search queries are stripped of emails, wallet addresses, UUIDs, long identifiers, and URLs; secret-like input is rejected instead of being sent externally. Returned snippets are treated as untrusted discovery metadata, not verified article contents. Every accepted result carries provider, publisher, URL, publication time when available, and fetch time into the Evidence Pack and Agent citation audit.

If both the synchronized pipeline and the controlled online search lack sufficient evidence, the Agent must say which evidence is missing and must not fill the gap from model memory.
