# Mock and fallback inventory
| Location | Capability | Status | Production rule |
|---|---|---|---|
| `packages/agents/llm/mock_provider.py` | Agent response | MOCK_ONLY | disabled unless explicitly enabled in non-production |
| `packages/agents/llm/provider_factory.py` | provider failure fallback | PARTIAL | capability must be DEGRADED/FAILED; never present mock as healthy |
| `packages/data/public_market_provider.py` | market fallback | PARTIAL | mock is allowed only with explicit mock mode; reject for Portfolio/Risk/Trading |
| `packages/data/mock_provider.py` | market fixture | MOCK_ONLY | tests/local demo only |
| `packages/data/bloomberg_provider.py` | Bloomberg mock | MOCK_ONLY | already rejected in production |
| `apps/web/lib/api.ts` | API fallback constants | FRONTEND_FALLBACK | production requests return `unavailable`; UI must render error/stale state |
| `apps/web/lib/api.ts` | integrations demo rows | FRONTEND_FALLBACK | remove from production pages before public launch |
| Nautilus quant fixtures | backtest | MOCK_ONLY | research fixture only; never label live or official performance |
| notification mock providers | delivery | MOCK_ONLY | development/test only; real delivery requires provider credentials |
Every mock response used by a real endpoint must carry `is_mock=true`, `source=mock`, `environment` and `generated_at`. The current audit found some legacy UI constants that still need migration to this envelope.
