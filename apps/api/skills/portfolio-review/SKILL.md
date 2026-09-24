---
name: portfolio-review
description: Personal portfolio exposure, position, and risk-context review.
whenToUse: >-
  Use when the user asks for personal portfolio exposure, position, and risk-context review and the request should be answered from synchronized evidence rather than model memory.
metadata:
  legacy_slug: portfolio_review
  publisher: PureGamma AI
  version: "1.2.0"
  risk_level: low
  migrated_from: packages/skills/builtins.py
---

Use only the authenticated user's portfolio facts. Lead with the NAV summary: total NAV, 24h change in USD and percent, available cash, and per-account breakdown. Then discuss the largest holdings with their chain, oracle price, weight, and 24h change, and call out concentration, stablecoin share, and notable movers. Mark missing prices, stale snapshots, unverified contracts, fallback-priced native assets, and partial data. When no portfolio account is connected, say so plainly, explain what the review would cover once connected, and point to the Integrations page instead of returning a generic empty answer.

## Authorized data sources

portfolio, market

## Expected tools

get_account_snapshot, get_position_snapshot, get_open_orders, get_market_quote

## Boundaries

- Loading this skill grants no data source, tool or permission by itself; the
  server still applies entitlement, quota, billing and the tool allowlist of
  the running agent.
- Never fabricate a value, a citation or a timestamp. Report an unavailable
  provider and deliver the best partial answer with its evidence gaps.
