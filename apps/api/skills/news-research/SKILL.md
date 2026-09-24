---
name: news-research
description: Fresh, source-attributed news and market narrative research.
whenToUse: >-
  Use when the user asks for fresh, source-attributed news and market narrative research and the request should be answered from synchronized evidence rather than model memory.
metadata:
  legacy_slug: news_research
  publisher: PureGamma AI
  version: "1.2.0"
  risk_level: low
  migrated_from: packages/skills/builtins.py
---

Cluster repeated reports, distinguish reporting from opinion, and attach URLs and publication timestamps. When a news provider is unavailable (missing key, license, or sync error), say so once and continue with the remaining providers; never present a partial feed as the complete picture.

## Authorized data sources

rss, fintwit, x, x-twitter, bloomberg

## Expected tools

get_recent_news, search_news, search_source_documents, search_online_sources, get_sentiment_context

## Boundaries

- Loading this skill grants no data source, tool or permission by itself; the
  server still applies entitlement, quota, billing and the tool allowlist of
  the running agent.
- Never fabricate a value, a citation or a timestamp. Report an unavailable
  provider and deliver the best partial answer with its evidence gaps.
