# Agent Chat Architecture

## Request lifecycle

```text
Chat UI -> authenticated POST/SSE -> conversation ownership + quota
        -> financial lexicon + versioned Agent Runtime plan
        -> server Skill/entitlement resolution + Credit reservation
        -> deterministic allowlisted tool plan
        -> synchronized retrieval + Evidence Pack quality check
        -> versioned Prompt Registry -> OpenAI-compatible LLM composer
        -> SSE deltas/citations/status
        -> persisted answer, evidence, prompt refs, usage, and settlement
```

SSE events are `run.started`, `plan.ready`, `tool.started`, `tool.completed`, `evidence.ready`, `citation`, `message.delta`, `message.completed`, `run.failed`, and `run.canceled`. The two planning/evidence events are additive and safe for older clients to ignore.

The engineering boundaries and compatibility policy are defined in [AGENT_PLATFORM_BOUNDARIES.md](./AGENT_PLATFORM_BOUNDARIES.md).

## Read-only tools

- `get_market_quote` and `get_market_history` read persisted normalized market quotes.
- `get_recent_news` and `search_news` read sanitized synchronized RSS records.
- `get_defi_protocol_metrics` reads normalized DefiLlama metrics.
- `get_chain_metrics` and `get_onchain_snapshot` read synchronized RPC/subgraph metrics.
- `get_data_source_status` reads persisted provider health.

There is no arbitrary URL, SQL, GraphQL, RPC, shell, order, withdrawal, signing, or transaction tool.

## Reliability and security

Conversation IDs are UUIDs and every query includes `user_id`. Runs and assistant messages persist before generation. Failures preserve the user message and mark the run/message failed without recording successful product usage. Browser disconnects mark a run interrupted; stale pending/running rows are recovered after ten minutes.

The server system prompt treats user and retrieved content as untrusted, rejects instructions embedded in news, forbids fabricated data/citations, requires timestamps for time-sensitive claims, and preserves the research-only disclaimer.

Only recent messages plus an optional conversation summary are included in context. Tool results are truncated to the minimum useful evidence.

## Model configuration

```env
AGENT_PROVIDER=openai
AGENT_MODEL=your-model
OPENAI_API_KEY=...
AGENT_MAX_OUTPUT_TOKENS=1200
AGENT_TEMPERATURE=0.2
ENABLE_MOCK_AGENT=false
```

DeepSeek continues to work through the existing provider layer. If no real model key is configured and mock Agent mode is false, the run returns `MODEL_NOT_CONFIGURED`; it does not substitute a canned answer.
