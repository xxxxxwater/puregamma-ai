# Agent Architecture
Agents live in `packages/agents` and coordinate market data, risk scoring, strategy context, sentiment, and report writing.
Agent output is research only and must not be framed as personalized investment advice.
## Current Agents
| Agent | Purpose |
| --- | --- |
| `MarketDataAgent` | Gets market data from mock provider |
| `ResearchAgent` | Builds combined research context |
| `RiskAgent` | Produces portfolio-style risk summary from quotes |
| `SentimentAgent` | Sentiment abstraction |
| `StrategyAgent` | Strategy/playbook coordination |
| `ReportWriterAgent` | Renders daily report content |
| `RouterAgent` | Routing abstraction |
| `LLMClient` | OpenAI-compatible wrapper with mock fallback |
## Current Flow
```text
ResearchAgent
  -> MarketDataAgent
  -> RiskAgent
  -> market regime
  -> report or signal service
```
## LLM Behavior
`LLMClient` supports OpenAI-compatible calls when configured. If the OpenAI package or credentials are missing, it falls back to mock synthesis.
Configuration:
```text
LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_BASE_URL=
LLM_MODEL=
```
## Design Rules
- Keep provider calls outside report formatting where possible.
- Return structured data to services.
- Preserve source and timestamp metadata.
- Add credit checks before high-cost agent workflows.
- Avoid hidden trading recommendations.
## Future Work
- Add trace IDs across agent runs.
- Add source citations and freshness metadata to agent outputs.
- Add LLM budget controls and prompt/version logging.
- Add portfolio-aware research once NAV backend exists.
