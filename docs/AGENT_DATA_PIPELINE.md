# Agent Data Pipeline

## Flow

1. A provider fetches a bounded page using its persisted cursor and conditional headers.
2. The raw payload is saved before analysis.
3. Normalization sanitizes text and maps the record to the common document schema.
4. Stable content hashes remove duplicate articles/posts. Event fingerprints group related coverage.
5. Entity extraction links explicit BTC, ETH, SOL, HYPE, MSTR, and STRC mentions.
6. Topic and sentiment classifiers create traceable derived fields.
7. The weighted score is calculated as sentiment x credibility x freshness x engagement x asset relevance.
8. Repeated coverage of the same event is attenuated; it does not multiply confidence linearly.
9. The shared financial lexicon normalizes user asset aliases, task intent, and time horizon.
10. The Agent retrieves persisted documents by time, asset, topic, provider, and author.
11. Tool results are assembled into a versioned Evidence Pack and checked against the selected Skill/intent requirements.
12. Responses distinguish reported facts, attributed opinions, and AI inference, and include original URLs and timestamps.

## Retrieval behavior

`search_source_documents` is read-only and returns source type, author, title, summary, URL, UTC publication time, symbols, topics, sentiment components, credibility, weighted score, event fingerprint, and license state. FinTwit/X evidence is labeled as source opinion. RSS/Bloomberg metadata is labeled as reported evidence, not independently verified truth.

If no matching synchronized evidence exists, the Agent says that the connected sources do not contain enough information. It must not invent a citation, infer an asset link from generic text, treat mock Bloomberg data as real, or turn research into an order or automated trade.

## Alert replay protection

Normalized documents have stable hashes, event fingerprints, and `alert_processed_at`. Recent-event queries use a bounded UTC window, so old documents do not re-enter current alert candidates. Notification delivery retains its existing idempotency key and retry ledger.
