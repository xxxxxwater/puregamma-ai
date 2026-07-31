# PureGamma Agent Platform Boundaries

This document defines the compatibility boundary used while the product is in public preview. The existing Agent Chat API remains the public entry point; the implementation behind it is split into four independently versioned engineering domains.

## Runtime flow

```text
User goal
  -> deterministic financial lexicon
  -> Agent Runtime plan
  -> server-side Skill resolution and entitlement checks
  -> server-side Credit quote and reservation
  -> allowlisted tool plan
  -> Evidence Pack and sufficiency check
  -> versioned Prompt bundle
  -> configured LLM composer
  -> persisted answer, citations, usage, settlement, and next actions
```

## 1. Agent Runtime

Location: `packages/agents/runtime/`

The Runtime owns goal interpretation, high-level intent, missing-field detection, automatic Skill selection, evidence requirements, and continuity actions. Runtime plans are deterministic and versioned. A plan is persisted in `agent_messages.context_json.runtime` so production behavior can be audited without exposing model chain-of-thought.

The Runtime does not own provider credentials, market facts, Credit balances, Skill manifests, or trading state.

## 2. Prompt Engineering

Location: `packages/agents/prompts/`

System behavior is composed from versioned prompt templates. Identity, evidence policy, trading boundaries, and conversation experience are separate templates. Every Agent run records prompt references in the persisted runtime context and Skill usage metadata.

User response preferences are presentation hints only. They are lower priority than system safety, Skill contracts, evidence rules, entitlement, risk, and trading controls.

## 3. Lexicon and Evidence Pipeline

Locations: `packages/data/lexicon.py` and `packages/data/evidence.py`

The financial lexicon normalizes multilingual asset aliases, task intent, and time horizon without an LLM call. The Evidence Pack defines the common contract for quotes, source documents, portfolio snapshots, options snapshots, provider status, and strategy results.

An Evidence Pack reports `sufficient=false` and the missing evidence classes when requirements are not met. The model must disclose the gap and must not replace missing facts with model memory.

## 4. Skills Platform

Location: `packages/skills/`

Skills declare a versioned task contract: schemas, authorized tools, data sources, evidence rules, risk, cost, and runtime limits. Skills may reference prompt templates but do not own the Agent Runtime or data ingestion pipeline.

Chat is one Skill invocation entry point. Reports, Portfolio, Autopilot, backtests, and future workflow APIs use the same registry and audit records.

## User experience contract

- A user can state a goal without selecting tools, Skills, or data sources.
- Blank advanced settings mean server-side automatic selection, not a frontend default hidden from the server.
- The browser displays the server-generated quote; it never submits a task type or final usage amount.
- The UI shows detected intent, evidence sufficiency, traceable sources, actual Credits, and useful continuity actions.
- Advanced users may pin Skills, constrain data sources, select an eligible model, attach files, and set response preferences.
- Paid capabilities must communicate concrete added value. Product flows must not manufacture urgency or conceal cost.

## Compatibility policy

Legacy Skill slugs in `agent_messages.context_json.skills` remain accepted. New runs persist resolved `skill_id + version` references. The public SSE stream remains backward compatible and adds optional `plan.ready` and `evidence.ready` events. Existing clients that ignore unknown SSE events continue to work.
