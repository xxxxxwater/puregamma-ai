---
name: source-check
description: Provenance, freshness, licensing, and cross-source verification.
whenToUse: >-
  Use when the user asks for provenance, freshness, licensing, and cross-source verification and the request should be answered from synchronized evidence rather than model memory.
metadata:
  legacy_slug: source_check
  publisher: PureGamma AI
  version: "1.2.0"
  risk_level: low
  migrated_from: packages/skills/builtins.py
---

Do not infer truth from repetition. Report provenance, freshness, corroboration, and unresolved conflicts. Begin with get_data_source_status so the verification report can separate 'no corroboration found' from 'corroboration channel unavailable', and list unavailable channels explicitly.

## Authorized data sources

rss, fintwit, x, x-twitter, bloomberg, market

## Expected tools

get_data_source_status, search_source_documents, search_online_sources

## Boundaries

- Loading this skill grants no data source, tool or permission by itself; the
  server still applies entitlement, quota, billing and the tool allowlist of
  the running agent.
- Never fabricate a value, a citation or a timestamp. Report an unavailable
  provider and deliver the best partial answer with its evidence gaps.
