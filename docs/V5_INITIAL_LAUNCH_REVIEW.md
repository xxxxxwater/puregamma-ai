# PureGamma AI V5 Initial Launch Review

## Release decision

The repository is suitable for a controlled C-end beta only after launch-mode
gating and production configuration. It is not ready to expose every existing
route. Internal research, mock, admin, and runtime surfaces must remain hidden.

## Findings

### Critical

1. Frontend API failures silently return realistic-looking mock market, report,
   integration, and portfolio records. A customer can mistake generated fallback
   content for live facts.
2. `docker-compose.yml` publishes PostgreSQL, Redis, API, and runtime ports and
   uses a fixed database password. It is development-only and unsafe for a VPS.
3. Production deployment is incomplete: Web, Celery worker, scheduler, reverse
   proxy, TLS, backups, and restart/resource policies are absent.

### High

1. Consumer navigation exposes unfinished Data Sources, Integrations, Daily Push,
   Nautilus, Admin, strategy, signal, and trading-control surfaces.
2. Mock login is always registered. It must reject production requests even if a
   route is discovered directly.
3. Landing and dashboard content contains simulated NAV, PnL, mock freshness,
   institutional sales placeholders, and disabled-execution language inconsistent
   with the C-end product.
4. Missing provider keys may select mock LLM/notification behavior. Production
   must fail closed and report `NOT_CONFIGURED` instead of successful delivery.

### Medium

1. Report delivery still exposes Slack and Email despite the C-end scope being
   Telegram and iMessage.
2. Several documentation files describe planned providers as if they were product
   roadmap surfaces. They should not be linked from customer pages.
3. The iMessage relay cannot run on a Linux VPS and requires a separately managed
   macOS host.

## V5 initial customer surface

- Dashboard: live market context and source-aware brief access.
- Agent: sourced Beta, Alpha, and Long Gamma decision support.
- Reports: concise research with Telegram/iMessage delivery.
- Options: read-only Deribit chain, Greeks, and Long Gamma ranking.
- NAV: empty until a real user account API is connected.
- Billing and Account.

Internal routes remain in source code but are redirected in initial-launch mode.

## Positioning

PureGamma AI is an AI decision-support system for individual secondary-market
investors. It helps users understand Beta exposure, discover evidence-backed Alpha,
and evaluate Long Gamma opportunities with explicit data sources and risk context.
It does not promise returns, custody assets, or silently execute trades.
