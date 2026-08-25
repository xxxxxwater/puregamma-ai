# PureGamma AI Documentation
This documentation turns PureGamma AI from a code project into an operating manual for users, developers, administrators, operators, and enterprise customers.

For the complete scope of the current MVP upgrade, including what was added,
the technologies adopted, and availability boundaries, see
[MVP Upgrade — 2026-07-24](./release/MVP_20260724_UPGRADE.md).
## Current Implementation Status
| Area | Status |
| --- | --- |
| Web dashboard | Implemented |
| FastAPI backend | Implemented |
| Auth mock login | Implemented |
| Reports, signals, playbooks | Implemented with mock market data |
| Stripe Billing, Payment Links, credits, entitlements | Implemented |
| LLM provider abstraction and DeepSeek adapter | Implemented |
| Notifications: email, Telegram, Slack, iMessage mock/relay | Implemented |
| iMessage macOS relay | Implemented |
| Workers and scheduler | Implemented |
| Executable strategy specs + compiler + agent backtest tools | Implemented |
| DeepSeek Harness deep research | Phase 1 foundation; flags default OFF |
| Memory service | Phase 1 foundation; flag default OFF |
| Trading mandate foundation (PAPER/SHADOW audits) | Phase 1 foundation; flags default OFF |
| Server-computed Portfolio NAV | Implemented; freshness is explicit and stale valuations are never fabricated |
| Plaid, IBKR, and Hyperliquid portfolio connectors | Implemented behind configured credentials and source freshness checks |
| NautilusTrader runtime | Implemented as an isolated BACKTEST/PAPER/SHADOW execution data plane; LIVE remains gated and disabled by default |
| Bloomberg import | Planned enterprise import |
## Product
- [Overview](./product/OVERVIEW.md)
- [Pricing and Plans](./product/PRICING_AND_PLANS.md)
- [Daily Brief](./product/DAILY_BRIEF.md)
- [Portfolio NAV](./product/PORTFOLIO_NAV.md)
- [Signals and Playbooks](./product/SIGNALS_AND_PLAYBOOKS.md)
- [PRD](./product/PRD.md)
## Getting Started
- [Quickstart](./getting-started/QUICKSTART.md)
- [Local Development](./getting-started/LOCAL_DEVELOPMENT.md)
- [Environment Variables](./getting-started/ENVIRONMENT_VARIABLES.md)
- [Mock Mode](./getting-started/MOCK_MODE.md)
- [Docker Compose](./getting-started/DOCKER_COMPOSE.md)
## Deployment
- [Deployment Overview](./deployment/DEPLOYMENT_OVERVIEW.md)
- [Production Checklist](./deployment/PRODUCTION_CHECKLIST.md)
- [Workers and Scheduler](./deployment/WORKERS_AND_SCHEDULER.md)
- [Database and Redis](./deployment/DATABASE_AND_REDIS.md)
- [Secrets Management](./deployment/SECRETS_MANAGEMENT.md)
- [Observability](./deployment/OBSERVABILITY.md)
## Integrations
- [Stripe](./integrations/STRIPE.md)
- [DeepSeek](./integrations/DEEPSEEK.md)
- [iMessage Relay](./integrations/IMESSAGE_RELAY.md)
- [Telegram](./integrations/TELEGRAM.md)
- [Slack](./integrations/SLACK.md)
- [Email](./integrations/EMAIL.md)
- [Plaid](./integrations/PLAID.md)
- [Exchange Read-only Keys](./integrations/EXCHANGE_READONLY_KEYS.md)
- [On-chain Wallets](./integrations/ONCHAIN_WALLETS.md)
- [CoinDesk RSS](./integrations/COINDESK_RSS.md)
- [ChainCatcher Newswire](./integrations/CHAINCATCHER_NEWSWIRE.md)
- [X KOL](./integrations/X_KOL.md)
- [Bloomberg](./integrations/BLOOMBERG.md)
- [NautilusTrader](./integrations/NAUTILUS_TRADER.md)
## Developer
- [Architecture](./developer/ARCHITECTURE.md)
- [API Reference](./developer/API_REFERENCE.md)
- [Database Schema](./developer/DATABASE_SCHEMA.md)
- [Billing Architecture](./developer/BILLING_ARCHITECTURE.md)
- [LLM Provider Architecture](./developer/LLM_PROVIDER_ARCHITECTURE.md)
- [Adding a Data Provider](./developer/ADDING_DATA_PROVIDER.md)
- [Adding a Strategy](./developer/ADDING_STRATEGY.md)
- [Adding a Notification Provider](./developer/ADDING_NOTIFICATION_PROVIDER.md)
- [Agent Architecture](./developer/AGENT_ARCHITECTURE.md)
- [Credit and Entitlements](./developer/CREDIT_AND_ENTITLEMENTS.md)
- [Harness Research Architecture](./developer/HARNESS_RESEARCH_ARCHITECTURE.md)
- [Memory Architecture](./developer/MEMORY_ARCHITECTURE.md)
- [Automated Trading Foundation](./developer/AUTOMATED_TRADING_FOUNDATION.md)
- [Mobile API Contract](./mobile/MOBILE_API_CONTRACT.md)
## Admin
- [Admin Guide](./admin/ADMIN_GUIDE.md)
- [User Management](./admin/USER_MANAGEMENT.md)
- [Billing Operations](./admin/BILLING_OPERATIONS.md)
- [Data Source Monitoring](./admin/DATA_SOURCE_MONITORING.md)
- [Notification Deliveries](./admin/NOTIFICATION_DELIVERIES.md)
- [Incident Runbook](./admin/INCIDENT_RUNBOOK.md)
## Operations
- [Harness Research Runbook](./operations/HARNESS_RUNBOOK.md)
- [Trading Mandate Runbook](./operations/TRADING_MANDATE_RUNBOOK.md)
## Security
- [Security Overview](./security/SECURITY_OVERVIEW.md)
- [Data Privacy](./security/DATA_PRIVACY.md)
- [Secret Handling](./security/SECRET_HANDLING.md)
- [Tenant Isolation](./security/TENANT_ISOLATION.md)
- [iMessage Security](./security/IMESSAGE_SECURITY.md)
- [Harness Threat Model](./security/HARNESS_THREAT_MODEL.md)
- [Memory Privacy and Retention](./security/MEMORY_PRIVACY_AND_RETENTION.md)
## Compliance
- [Disclaimer Guide](./compliance/DISCLAIMER_GUIDE.md)
- [Investment Research Limits](./compliance/INVESTMENT_RESEARCH_LIMITS.md)
- [Backtest Disclosure](./compliance/BACKTEST_DISCLOSURE.md)
- [Portfolio NAV Disclosure](./compliance/PORTFOLIO_NAV_DISCLOSURE.md)
## Troubleshooting
- [Common Errors](./troubleshooting/COMMON_ERRORS.md)
- [Stripe Webhooks](./troubleshooting/STRIPE_WEBHOOKS.md)
- [iMessage Relay](./troubleshooting/IMESSAGE_RELAY.md)
- [Plaid Sync](./troubleshooting/PLAID_SYNC.md)
- [Portfolio NAV](./troubleshooting/PORTFOLIO_NAV.md)
- [Worker Queue](./troubleshooting/WORKER_QUEUE.md)
- [Nautilus](./troubleshooting/NAUTILUS.md)
## Recommended Reading Paths
New user:
1. [Overview](./product/OVERVIEW.md)
2. [Daily Brief](./product/DAILY_BRIEF.md)
3. [Portfolio NAV](./product/PORTFOLIO_NAV.md)
4. [Pricing and Plans](./product/PRICING_AND_PLANS.md)
Developer:
1. [Quickstart](./getting-started/QUICKSTART.md)
2. [Local Development](./getting-started/LOCAL_DEVELOPMENT.md)
3. [Architecture](./developer/ARCHITECTURE.md)
4. [API Reference](./developer/API_REFERENCE.md)
Operator or administrator:
1. [Deployment Overview](./deployment/DEPLOYMENT_OVERVIEW.md)
2. [Production Checklist](./deployment/PRODUCTION_CHECKLIST.md)
3. [Admin Guide](./admin/ADMIN_GUIDE.md)
4. [Incident Runbook](./admin/INCIDENT_RUNBOOK.md)
Enterprise customer:
1. [Security Overview](./security/SECURITY_OVERVIEW.md)
2. [Data Privacy](./security/DATA_PRIVACY.md)
3. [Tenant Isolation](./security/TENANT_ISOLATION.md)
4. [Investment Research Limits](./compliance/INVESTMENT_RESEARCH_LIMITS.md)
