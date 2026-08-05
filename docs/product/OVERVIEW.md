# Product Overview

PureGamma AI is an AI-native investment research SaaS for crypto and equity-aware portfolios. It helps active investors consume market intelligence, understand portfolio exposure, review research signals, and receive daily summaries without opening multiple tools.

PureGamma AI is research software only. It does not place trades, custody assets, provide tax advice, or promise returns. All investment content must include: `Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.`

## Who It Is For

- Active crypto investors who monitor BTC, ETH, SOL, HYPE, and related instruments daily.
- Investors with crypto plus equity proxy exposure such as MSTR.
- Small investment teams that want a repeatable daily research workflow.
- Enterprise customers evaluating private deployments and custom data sources.

It is not designed for high-frequency execution, brokerage order routing, custody, tax filing, or guaranteed signal performance.

## Core Workflow

1. Ingest market, sentiment, on-chain, macro, portfolio, and optional enterprise data.
2. Normalize the data into shared market intelligence.
3. Generate signals and strategy playbooks.
4. Produce daily market and portfolio-aware briefs.
5. Deliver selected alerts through email, Telegram, Slack, or iMessage.
6. Track usage through Stripe entitlements and credits.
7. Monitor system health through admin and runbook workflows.

## Product Surfaces

| Surface | Purpose | Current status |
| --- | --- | --- |
| Web dashboard | Research console and operational UI | Implemented |
| Daily push | iMessage-style daily brief | UI and notification path implemented; scheduling uses worker tasks |
| Reports | Daily, event, and playbook reports | Implemented |
| Signals | Market-structure research signals | Implemented with mock provider data |
| Portfolio | Consolidated NAV and exposure | Frontend fallback data; backend planned |
| Integrations | Plaid, exchanges, wallets, notifications | Frontend fallback plus docs; selected notification providers implemented |
| Admin | Users, reports, Stripe events, notifications | Implemented behind admin role |

## Important Limits

- Market providers are mock-first and several adapters are placeholders.
- Portfolio NAV, Plaid, exchange sync, and wallet sync need backend implementation before production use.
- NautilusTrader is documented as a target research layer; current backend uses a mock backtest engine.
- iMessage delivery requires a self-hosted Mac relay and has platform limitations.

## Related Docs

- [Quickstart](../getting-started/QUICKSTART.md)
- [Architecture](../developer/ARCHITECTURE.md)
- [Security Overview](../security/SECURITY_OVERVIEW.md)
- [Disclaimer Guide](../compliance/DISCLAIMER_GUIDE.md)
