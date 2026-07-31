# PureGamma AI V3 Commercial Design

## Positioning

PureGamma AI V3 is an AI operating system for secondary-market investors. The
commercial product focuses on concise sourced research, portfolio visibility,
controlled execution, recurring delivery, and subscription billing. It is not
presented as a strategy marketplace, signal leaderboard, or backtest workbench.

## Customer surface

1. Dashboard: market context, portfolio condition, recent RSS events, account risk.
2. Agent: short answers with source links, explicit fact/inference separation,
   portfolio-aware explanations, and controlled execution intents.
3. Reports: concise research briefs generated from traceable RSS and licensed data.
4. Portfolio: real account positions, balances, PnL, exposure, and reconciliation.
5. Data sources: RSS, licensed X/FinTwit, Bloomberg when authorized, and public
   market prices. Missing credentials must be displayed as unconfigured.
6. Runtime: account connection, execution review, risk limits, order lifecycle,
   reconciliation, and emergency stop.
7. Delivery: Telegram and self-hosted iMessage Mac Relay.
8. Billing: Stripe plans, entitlements, credits, and customer portal.

Signals, strategy authoring, and backtests are removed from customer navigation.
Their existing domain models remain internal until data migration and retention
requirements permit deletion.

## Execution safety

LIVE is a per-account commercial capability, never a global always-on flag. It
requires an approved exchange adapter, encrypted secret reference, read/trade-only
permissions, account allowlisting, explicit activation, per-order risk checks,
notional and loss limits, reconciliation, audit logs, and a kill switch. Withdrawal,
transfer, wallet signing, and custody permissions are forbidden.

The Agent may prepare an execution intent but cannot silently submit it. The
runtime is the only service allowed to reach an exchange trading endpoint.

## Commercial tiers

- Core: sourced RSS research, dashboard, Telegram, read-only portfolio.
- Pro: Agent research, more feeds, iMessage relay, portfolio reconciliation.
- Execution: approved live adapter, stricter onboarding, risk controls, audit log.
- Enterprise: licensed Bloomberg/X connections, team controls, private deployment.

## Release gates

- Security review of exchange credential storage and tenant isolation.
- Exchange sandbox certification and order-state reconciliation tests.
- Legal review for jurisdiction, suitability messaging, data licensing, and terms.
- Operational runbooks for stale data, partial fills, rate limits, and emergency stop.
- LIVE remains disabled until every gate is signed off for the target deployment.
