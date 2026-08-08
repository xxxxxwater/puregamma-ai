# PureGamma AI Skills Library
## Purpose
PureGamma Skills are versioned, declarative research capabilities. They are not
arbitrary prompt strings and they do not execute imported code. Every invocation
is resolved through the same registry before a project surface can use a Skill.
The original Agent Chat capabilities are now official Skills at version `1.0.0`:
- `market_research`
- `news_research`
- `portfolio_review`
- `options_analysis`
- `source_check`
- `deep_research`
Legacy clients may continue sending these slugs in `skills`. New clients send
`skill_refs` containing `skill_id`, `version`, and optionally `installation_id`.
Persisted Agent context uses the versioned reference and no longer relies on a
bare string array.
## Architecture
```text
Chat / Dashboard / Reports / Portfolio / Autopilot / Nautilus / API / Jobs
                               v
                    packages.skills.SkillRegistry
                     |          |           |
                  visibility  permission  runtime limits
                     |          |           |
                     +------ SkillVersion --+
                    evidence + usage + cost audit
                           skill_runs
```
The registry is the product boundary. UI labels never grant data or tool access.
A caller supplies an authenticated `SkillActor`, trigger source, exact Skill
reference, requested capabilities, and expected cost. The registry resolves the
pinned version and enforces scope, installation, release state, plan, rate,
Autopilot, order-intent, schema, and cost constraints.
## Manifest contract
```yaml
schema_version: "1.0"
skill_id: "0a4779cc-4790-4eca-9f70-ac64f20b35f9"
slug: custom_market_check
name: Custom Market Check
description: Evidence-based personal market review.
publisher: Example Research
asset_classes: [crypto]
data_sources: [market, rss]
tool_allowlist: [get_market_quote, search_source_documents]
input_schema:
  type: object
  properties:
    query: {type: string}
  required: [query]
output_schema:
  type: object
  properties:
    answer: {type: string}
    citations:
      type: array
      items: {type: object}
prompt_template_ref: prompts/main.md
workflow_template_ref: null
strategy_template_ref: null
risk_level: low
allow_autopilot: false
allow_order_intent: false
billing_type: included
version: 1.0.0
release_status: draft
scope: personal
evidence:
  required: true
  require_source_timestamp: true
  require_citation_links: true
  allow_insufficient_evidence_result: true
runtime:
  max_calls_per_hour: 20
  max_credits_per_run: 30
  timeout_seconds: 60
  human_confirmation_required: false
```
Unknown manifest fields fail validation. JSON schemas accept only a bounded,
deterministic subset and may not load remote references.
## Import boundary
`POST /api/skills/import` accepts a text-only bundle. GitHub provenance requires
a canonical HTTPS repository URL and a full 40-character commit hash. The API
does not clone a repository, resolve a branch, install dependencies, or execute
bundle content.
Allowed content is limited to:
- `.puregamma-skill.yaml`
- Markdown/text prompt templates
- YAML/JSON strategy and Nautilus configuration
- YAML/JSON data-source mapping
- JSON schemas
- Markdown/text documentation and declarative examples
Paths are normalized and traversal, absolute paths, executable extensions,
remote JSON Schema references, oversized files, unsupported tools, unreviewed
order-intent access, and conflicting versions are rejected.
Ordinary users can publish only personal declarative Skills. Official,
marketplace, workspace, high-risk, and execution-sensitive releases require the
corresponding reviewed administration or confirmation workflow. User code
execution remains unavailable.
## Persistence and audit
| Table | Responsibility |
| --- | --- |
| `skills` | Identity, owner, scope, status, and current version |
| `skill_versions` | Immutable manifest/content snapshot and validation result |
| `skill_installations` | User/workspace enablement, pinned version, overrides |
| `skill_runs` | Trigger, hashed input summary, output summary, evidence, usage, cost, error |
| `skill_permissions` | Versioned data-source and tool grants |
| `skill_sources` | Official/upload/GitHub provenance, commit, and trust state |
Agent runs allocate reservation and settlement Credits across their selected
Skill audit rows. Actual Skill cost is capped by the smallest selected runtime
limit; overruns are absorbed by the platform rather than silently exceeding the
manifest. Raw user prompts are not copied into `skill_runs`; the audit stores a
SHA-256 digest, length, and permitted data sources.
## API surface
- `GET /api/skills`
- `GET /api/skills/{skill_id}`
- `POST /api/skills/import`
- `POST /api/skills/{skill_id}/install`
- `DELETE /api/skills/installations/{installation_id}`
- `GET /api/skills/installations`
- `GET /api/skills/runs`
- `POST /api/skills/validate-invocation`
`validate-invocation` is the shared adapter for Dashboard, reports, portfolio,
Autopilot, Nautilus, API, scheduled jobs, and future workflow entry points. The
Python `SkillRegistry` is used directly by trusted backend services so internal
workers do not depend on a browser API call.
Current project integrations use that same path:
- Agent Chat resolves exact versions, constrains tools, applies Skill templates,
  and settles the related `skill_runs` records.
- Event reports accept optional `skill_refs` and retain report evidence in the
  Skill audit.
- General and strategy-scoped backtests require the selected Skill to allow the
  Nautilus backtest tool.
- Portfolio Autopilot persists approved Skill references and validates them for
  both manual and scheduled worker runs.
- PAPER/SHADOW activation previews fail closed when a selected Skill lacks the
  explicit order-intent capability. Imported personal code/config cannot grant
  that capability.
- Dashboard and future product surfaces can preflight the same policy through
  `validate-invocation`; trusted backend callers use `SkillRegistry` directly.
## Future code execution
Supporting user code requires a separate sandbox runtime and a new reviewed
manifest capability. It must provide process/container isolation, CPU and memory
limits, an immutable filesystem, network allowlists, no inherited environment or
secrets, execution deadlines, structured logs, artifact scanning, audit trails,
and human review. The current runtime intentionally provides none of these code
execution paths.
