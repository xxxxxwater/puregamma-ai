---
name: options-analysis
description: Options surface, Greeks, and long-gamma research.
whenToUse: >-
  Use when the user asks for options surface, greeks, and long-gamma research and the request should be answered from synchronized evidence rather than model memory.
metadata:
  legacy_slug: options_analysis
  publisher: PureGamma AI
  version: "1.1.0"
  risk_level: medium
  migrated_from: packages/skills/builtins.py
---

State expiry, strike, timestamp, liquidity limitations, and assumptions for every options conclusion. When the options data feed is unavailable or stale, mark the affected instruments and limit conclusions to what fresh data supports.

## Authorized data sources

options, market

## Expected tools

get_options_context, get_earnings_gamma, get_market_quote

## Boundaries

- Loading this skill grants no data source, tool or permission by itself; the
  server still applies entitlement, quota, billing and the tool allowlist of
  the running agent.
- Never fabricate a value, a citation or a timestamp. Report an unavailable
  provider and deliver the best partial answer with its evidence gaps.
