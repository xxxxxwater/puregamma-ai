# Memory Privacy and Retention

Scope: the PureGamma-owned Memory Service (short-term conversation summaries
and medium-term `user_memories`).

## 1. Principles

- **User ownership**: all memory is user-scoped, user-visible, editable and
  deletable. Export includes audit metadata.
- **Least data**: only small, relevant, unexpired, consent-scoped entries
  are ever injected into a model context.
- **Never trading input**: no memory entry can authorize, alter, or inform
  trading decisions, risk limits, capital sizing, leverage, kill switch or
  order permissions. The `trading` namespace rejects writes by policy.
- **No secrets**: proposals and summaries are scanned against secret
  patterns (API keys, private keys, bearer tokens, connection strings, long
  account numbers) and rejected or redacted.

## 2. What may be stored

Language/display preferences; watchlists; confirmed research hypotheses;
unfinished research tasks; secretary todos; conversation summaries (goals,
known facts, used evidence, open questions, explicit user preferences).

## 3. What may never be stored

Raw full chat transcripts in medium-term memory; model-inferred personality,
risk appetite or investment capability; transient prices, unverified news or
sentiment judgments; account balances, trading keys, order secrets or
payment data; anything that could influence automated trading funds or risk
limits.

## 4. Retention schedule

| Data | Retention |
|---|---|
| Conversation summaries | conversation deletion (cascade) or 30 days (`MEMORY_SUMMARY_TTL_DAYS`) |
| User memories | per-kind TTL or user-managed; expired rows become `status=expired` via `expire_stale` |
| MemoryProposals | kept as consent evidence; idempotent by key |
| MemoryAuditRecords | `AUDIT_LOG_RETENTION_DAYS` policy |
| Harness JSONL session logs | short TTL after run end; never host-visible |

## 5. Consent model

- `created_by`: `user_confirmed | deterministic | model_proposed`.
- `consent_scope`: `chat | secretary | research | none` (portfolio defaults
  to `none`).
- Auto-accept applies only to low-risk deterministic kinds and can be
  disabled (`MEMORY_AUTO_ACCEPT_LOW_RISK=false`).
- Users can reject pending proposals, disable a whole scope, and delete
  individual entries or namespaces at any time.

## 6. Access control

- All service methods filter by `user_id` (multi-tenant isolation).
- Read injection (`retrieve_for_context`) is namespace/consent-filtered and
  salience-capped; reads update `last_used_at` and write an audit record.
- Memory is untrusted context: it cannot override system policy, Skill
  permissions, Evidence Packs, risk or trading boundaries.

## 7. Harness boundary

- Independent session ID per run; no cross-run/cross-user session reuse.
- Harness receives only API-provided summaries and permission-filtered
  memory; it cannot enumerate or search conversation history.
- Harness output can only produce `memory_proposals`; direct persistence is
  impossible by contract.

## 8. Verification

`tests/security/test_memory_service.py` covers tenant isolation, TTL,
rejection of secrets, trading-namespace write block, scope settings,
export, and the assertion that no memory can become trading input.
