---
name: deep-research
description: Broader multi-source research with a higher evidence and cost budget.
whenToUse: >-
  Use when the user asks for broader multi-source research with a higher evidence and cost budget and the request should be answered from synchronized evidence rather than model memory.
metadata:
  legacy_slug: deep_research
  publisher: PureGamma AI
  version: "1.2.0"
  risk_level: medium
  migrated_from: packages/skills/builtins.py
---

Build an evidence pack before synthesis. Present competing hypotheses, missing evidence, timestamps, and citations. When the user asks about strategy quality or a trading idea, prefer validating it with run_nautilus_backtest and get_strategy_performance over narrative-only reasoning, and report the backtest window, assumptions, and key performance metrics alongside the thesis. Skip unavailable providers with a one-line disclosure instead of aborting the research.

## Authorized data sources

market, rss, fintwit, x, x-twitter, bloomberg, portfolio, options, onchain, defillama

## Expected tools

get_market_quote, get_market_history, search_source_documents, search_online_sources, get_defi_protocol_metrics, get_chain_metrics, get_data_source_status, get_account_snapshot, get_position_snapshot, get_options_context, list_research_strategies, run_nautilus_backtest, get_strategy_performance

## Boundaries

- Loading this skill grants no data source, tool or permission by itself; the
  server still applies entitlement, quota, billing and the tool allowlist of
  the running agent.
- Never fabricate a value, a citation or a timestamp. Report an unavailable
  provider and deliver the best partial answer with its evidence gaps.
