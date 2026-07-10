# Adding a Data Provider

Data providers live in `packages/data`.

New provider output can influence investment research, so source freshness, attribution, and disclaimers matter.

## Existing Pattern

Market providers implement or mimic `MarketDataProvider`:

```python
class MarketDataProvider(ABC):
    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        raise NotImplementedError

    def get_market_regime(self, quotes: list[MarketQuote]) -> str:
        raise NotImplementedError
```

## Steps

1. Create a provider module in `packages/data`.
2. Return typed objects or normalized dicts, not raw vendor payloads.
3. Add environment variables to `.env.example`.
4. Document required keys in [Environment Variables](../getting-started/ENVIRONMENT_VARIABLES.md).
5. Add caching and rate-limit handling.
6. Add source freshness metadata.
7. Route it through the relevant agent or service.
8. Add admin source status.
9. Add tests for success, provider failure, and stale data.

## Provider Checklist

- Does it expose secrets only server-side?
- Does it preserve source timestamp?
- Does it handle rate limits?
- Does it distinguish stale, missing, and partial data?
- Does it avoid overclaiming precision?
- Does it include licensing restrictions if applicable?

## Example Skeleton

```python
from packages.data.base import MarketDataProvider, MarketQuote

class ExampleProvider(MarketDataProvider):
    def get_snapshot(self, symbols: list[str]) -> list[MarketQuote]:
        # Fetch, normalize, and return MarketQuote rows.
        raise NotImplementedError

    def get_market_regime(self, quotes: list[MarketQuote]) -> str:
        # Keep deterministic enough for tests.
        return "Mixed consolidation"
```

## Production Notes

- Do not let one provider outage fail the whole daily brief.
- Use fallback or partial-data warnings.
- Log provider name, status, and safe error code.
- Never log API keys or full raw payloads containing user data.
