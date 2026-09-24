---
name: market-research
description: Evidence-based market structure, price, and trend research.
whenToUse: >-
  Use when the user asks for evidence-based market structure, price, and trend research and the request should be answered from synchronized evidence rather than model memory.
metadata:
  legacy_slug: market_research
  publisher: PureGamma AI
  version: "1.3.0"
  risk_level: low
  migrated_from: packages/skills/builtins.py
---

Build the current-market evidence pack before synthesis. First call get_data_source_status and treat DEGRADED, ERROR, NEED_KEY, or NOT_CONNECTED providers as unavailable: state their unavailability once, then continue with the remaining healthy providers instead of stopping. Pair a fresh timestamped quote with traceable source documents. Search the controlled public web only when synchronized documents are insufficient. Separate observations, reported facts, source opinion, calculations, and inference. Always deliver the best partial answer from available evidence and end with a short 'evidence gaps' list; never fill gaps from model memory.

## Authorized data sources

market, rss, fintwit, x, x-twitter, bloomberg

## Expected tools

get_market_quote, get_market_history, search_source_documents, search_online_sources, get_data_source_status

## Boundaries

- Loading this skill grants no data source, tool or permission by itself; the
  server still applies entitlement, quota, billing and the tool allowlist of
  the running agent.
- Never fabricate a value, a citation or a timestamp. Report an unavailable
  provider and deliver the best partial answer with its evidence gaps.
