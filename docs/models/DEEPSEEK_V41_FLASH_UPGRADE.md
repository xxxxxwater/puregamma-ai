# DeepSeek V4.1 Flash Upgrade

DeepSeek released **DeepSeek V4.1 Flash** on **2026-09-10**. This document is
the authoritative record of how PureGamma moved its own default model onto it,
which calls changed, and how to roll back.

Source: <https://api-docs.deepseek.com/news/news260910> ·
Pricing: <https://api-docs.deepseek.com/quick_start/pricing/> ·
Thinking mode: <https://api-docs.deepseek.com/guides/thinking_mode>

## 1. Model identity (read this first)

| Thing | Value |
| --- | --- |
| Display name (what users see) | `DeepSeek V4.1 Flash` |
| Official API model name (what we send) | `deepseek-flash` |
| Retired names still accepted upstream | `deepseek-v4-flash`, `deepseek-v4-flash-0731`, `deepseek-v4-flash-vision-exp` |
| Retirement scheduled | `deepseek-v4-pro` routes to V4.1 Flash from 2026-09-14 12:00 Beijing time |
| Context / output limit | 1,048,576 / 393,216 tokens |

**Never** build a model id from the display name. `deepseek-v4.1-flash` does not
exist and must not appear in configuration.

`GET https://api.deepseek.com/models` on the production key returns exactly
`deepseek-flash` and `deepseek-v4-pro`, and a chat completion requested with the
legacy `deepseek-v4-flash` name answers with `"model": "deepseek-flash"`.

## 2. Defaults and precedence

| Setting | Default | Meaning |
| --- | --- | --- |
| `DEEPSEEK_MODEL` | `deepseek-flash` | Upstream model id sent to DeepSeek |
| `DEEPSEEK_THINKING_MODE` | `disabled` | DeepSeek defaults to thinking/effort=high; these paths opt out |
| `DEEPSEEK_REASONING_EFFORT` | `high` | Only used when thinking is enabled |
| `LLM_PROVIDER` | `deepseek` (production) | Selects the platform provider |
| `AGENT_MODEL` | empty | When set, overrides the resolved Agent default |
| `AGENT_PROVIDER` | empty | Falls back to `LLM_PROVIDER` |
| `HARNESS_RESEARCH_MODEL` | empty | Gateway **public** id for Harness; empty follows `DEEPSEEK_MODEL` |
| `OPENAI_LUNA_AUTO_ROUTE` | `false` | Automatic routing to the Luna lane |
| `KIMI_AUTO_ROUTE` | `false` | Automatic routing to the Kimi lane |

Resolution order for the effective upstream model is implemented once in
`apps/api/config.py`:

```
Settings.deepseek_effective_model
  -> normalize_deepseek_model(DEEPSEEK_MODEL)
     -> legacy name ? the model that actually serves it : the name unchanged
```

`provider_factory.llm_status()` reports both the effective `model` and the raw
`configured_model`, so a stale environment value is visible rather than hidden.

## 3. Automatic routing vs explicit choice

Every **automatically routed** task runs on DeepSeek V4.1 Flash: `agent_chat`,
`secretary_dialog`, `default_chat`, `daily_market_report`, `classification`,
`summarization`, portfolio/strategy/backtest review, `luna_research`, and the
long-context research tasks (`agent_deep_research`, `deep_research`,
`document_synthesis`, `source_crosscheck`, `kimi_research`).

The historical Kimi and Luna lanes are **not deleted**. They are opt-in:

* `KIMI_AUTO_ROUTE=true` restores Kimi for its long-context task types.
* `OPENAI_LUNA_AUTO_ROUTE=true` restores Luna for its deep-analysis task types.

An **explicit** choice is never rewritten:

* A user who selects `gpt-5.6-luna` in the Agent model picker gets Luna
  (still gated by plan and `OPENAI_LUNA_ENABLED`).
* A Gateway customer who names `kimi-k3-max`, `glm-5.2` or `deepseek-v4-pro`
  gets that upstream model.

## 4. Model call inventory

| Entry point | Call path | Before | After |
| --- | --- | --- | --- |
| Agent chat / secretary | `agent_service` → `get_llm_provider` → `DeepSeekProvider` | `deepseek-v4-flash` | `deepseek-flash` |
| Daily brief / report | `report_service.generate_daily_brief` → `get_llm_provider` | `deepseek-v4-flash` | `deepseek-flash` |
| Playbook / event report | `report_service` → provider abstraction | `deepseek-v4-flash` | `deepseek-flash` |
| Task router (chat, classification, summaries) | `ModelRouter.route_for_task` | `deepseek-v4-flash` | `deepseek-flash` |
| Task router (research/analysis lanes) | `ModelRouter.route_for_task` | `kimi` / `openai` | `deepseek-flash` (opt-in flags restore) |
| Multi-model research pipeline | `ModelRouter.deep_research` | Kimi + Luna + DeepSeek | single DeepSeek synthesis; skipped lanes recorded |
| Harness research run | `harness_run_service` → `gateway.service.execute_chat` | hard-coded `deepseek-v4-flash` | `settings.harness_effective_model` |
| Gateway (中转站) `/v1/chat/completions` | `gateway.service.execute_chat` → provider adapter | catalog public ids | catalog public ids incl. `deepseek-flash` |
| Gateway `/v1/models` | `gateway.service.model_list` | DB active models | DB active models incl. `deepseek-flash` |
| Admin LLM status | `provider_factory.llm_status` | raw configured name | effective model + raw name |
| Workers / scheduler | via the same services | `deepseek-v4-flash` | `deepseek-flash` |

## 5. Gateway (中转站) activation

Editing `config/gateway/providers.yaml` is **not** sufficient: routing reads
database records. Run the idempotent activation script after deploying:

```bash
python -m scripts.activate_deepseek_v41_flash --dry-run
python -m scripts.activate_deepseek_v41_flash --approve --approved-by <admin-user-id>
```

It bootstraps the catalog (upsert by `public_id`), syncs provider metadata,
creates a *pending* price revision when reviewed prices differ, and approves
only DeepSeek revisions on explicit request. Re-running is safe.

A model becomes routable only when it has an approved, active price revision.
Other providers' pending revisions are never touched.

## 6. Pricing notes

The catalog stores **off-peak** USD prices converted at the operator-approved
6.6 CNY/USD rate. DeepSeek charges a peak tariff — Monday to Friday
09:00-12:00 and 14:00-18:00 Beijing time — at **exactly 2x** the off-peak rate.

| Model | CNY off-peak (cache / input / output) | USD off-peak per 1M |
| --- | --- | --- |
| `deepseek-flash` | 0.02 / 1 / 4 | 0.00303030 / 0.15151515 / 0.60606061 |
| `deepseek-v4-pro` | 0.15 / 4.5 / 13.5 | 0.02272727 / 0.68181818 / 2.04545455 |

Two accounting rules are enforced in `packages/gateway/pricing.py`:

* `reasoning_tokens` is a **subset** of `completion_tokens` and is subtracted
  before the output tariff is applied.
* `cache_tokens` is a **subset** of the prompt and is billed at the cache
  tariff instead of the input tariff.

Historical request logs and ledger rows are never rewritten.

## 7. Rollback

Roll back in this order; each step is independent.

1. **Routing only (no rebuild).** Set `KIMI_AUTO_ROUTE=true` and/or
   `OPENAI_LUNA_AUTO_ROUTE=true` in the production `.env` and restart the
   `api`, `worker` and `scheduler` containers. This restores the previous
   automatic routing without a code change.
2. **Images.** The previous images are tagged before every build, for example
   `puregamma-ai-api:rollback-pre-v41-<timestamp>`. Point the compose override
   back at them and recreate the services:
   `docker compose -f docker-compose.production.yml -f docker-compose.v41-override.yml up -d --force-recreate api worker scheduler web`.
   Removing `docker-compose.v41-override.yml` entirely returns every service to
   its `build:` definition.
3. **Environment.** A timestamped copy of the pre-upgrade `.env` is written to
   `/var/backups/puregamma/.env.pre-v41-*`. Restore it and restart the API,
   worker and scheduler.
4. **Model name.** Setting `DEEPSEEK_MODEL=deepseek-v4-flash` is accepted
   upstream, but be aware that this does **not** restore the old V4 Flash
   model: DeepSeek retired it and serves V4.1 Flash for either name. Rolling
   the string back cannot bring the old model back.
5. **Database.** Migration `0031_deepseek_v41_flash_defaults` only changes a
   server default and is reversible with `alembic downgrade -1`. No historical
   row was modified, so downgrading corrupts nothing. The data backup taken
   before the upgrade is `/var/backups/puregamma/postgres-<timestamp>.dump`.
6. **Gateway catalog.** Restoring the previous `config/gateway/providers.yaml`
   and re-running the activation script creates a new *pending* revision for
   the old prices; it must be approved before the old price applies.
   Previously approved revisions are marked `superseded`, never deleted, so
   historical billing records keep their original tariff.

## 8. Verification

```bash
# offline contract tests
python -m pytest tests/unit/test_model_router.py tests/unit/test_llm_provider.py
python -m pytest tests/unit/test_deepseek_v41_flash_provider.py
python -m pytest tests/gateway tests/security/test_harness_contract.py
```

Production acceptance must exercise the real upstream, not a mock:

```bash
# 1. the model the deployment actually resolves
docker exec -e PYTHONPATH=/app -w /app puregamma-ai-api-1 python -c \
  "from apps.api.config import get_settings as g; s=g(); print(s.deepseek_effective_model, s.deepseek_thinking_enabled)"

# 2. the Gateway catalog and an external call
curl -s https://api.puregamma.ai/gateway/catalog | head -c 400
curl -s https://api.puregamma.ai/v1/models -H "Authorization: Bearer sk-pg-..."

# 3. confirm the log rows name the model that really ran
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -c \
  "select created_at, provider, model, task_type, status from llm_call_logs order by created_at desc limit 5;"
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -c \
  "select public_model, status, input_tokens, output_tokens, reasoning_tokens, retail_cost_usd from gateway_request_logs order by created_at desc limit 5;"
```

`routing.prompt_tokens`/`completion_tokens` come from the provider's `usage`
object, and `reasoning_tokens` is carried separately because DeepSeek includes
it inside `completion_tokens`.

## 9. Known limitations at the time of this upgrade

* **Homepage product preview.** Completed after the backend rollout; see
  section 10. `apps/web/app/[locale]/page.tsx` renders the announcement plus
  `apps/web/components/model-upgrade.tsx`, which reads availability, ids,
  context window and reviewed price from the same catalog the deployment serves
  (`lib/model-catalog.ts` holds the framework-neutral reader so a Server
  Component can call it without a client-reference proxy). The API docs page
  (`/zh/api`, `/en/api`) additionally lists **every** catalog model, so a model
  the deployment starts serving appears before anyone writes copy for it.
* **Kimi lane.** `kimi-k3-max` remains `pending` with no approved price
  revision, exactly as before this upgrade. `KIMI_AUTO_ROUTE=true` therefore
  degrades to DeepSeek until an operator approves the Moonshot price.
* **Peak/off-peak pricing.** The catalog stores off-peak USD prices. DeepSeek
  charges 2x during peak hours; the extra cost currently lands on the margin
  rather than on the customer.
* **Specialised models were not migrated.** Speech synthesis/recognition,
  embeddings and reranking do not run on DeepSeek; their providers and model
  ids are unchanged (see the audit table in the deployment report).
* **Pre-existing e2e failures are unrelated to this upgrade.** 15 Playwright
  specs fail on a clean checkout of `main` for the same reason as on this
  branch (verified by stashing this change and re-running): stale expectations
  against copy that changed in earlier commits (`i18n` landing/dashboard/daily
  push, `mobile-nav`, `mstr-btc`, `nautilus`, `integrations`, `daily-push`,
  `dashboard`, `portfolio`). They are listed here so the next person does not
  attribute them to the V4.1 Flash work. The new
  `tests/e2e/playwright/model-upgrade.spec.ts` passes 12/12.

## 10. Frontend surface (what the user actually sees)

The backend upgrade is invisible until the frontend admits it. This is the
frontend half, delivered separately from the model rollout:

| Surface | File | Reads from |
| --- | --- | --- |
| Homepage announcement + product preview | `apps/web/app/[locale]/page.tsx`, `apps/web/components/model-upgrade.tsx` | `GET /gateway/catalog`, server-rendered |
| Agent Chat model label and status | `apps/web/components/agent-chat.tsx` | `GET /api/agent/capabilities` for the selector, catalog for the status |
| API docs model cards + full catalog table | `apps/web/components/api-docs-embed.tsx` | `GET /gateway/catalog`, browser-fetched |
| Chat failure copy and request reference | `apps/web/lib/chat-errors.ts` | HTTP status, error code, `x-request-id` |
| Catalog reading helpers (no React) | `apps/web/lib/model-catalog.ts` | pure functions over `GatewayCatalog` |

Rules this frontend work follows, so it cannot drift from the deployment:

1. **Availability is never asserted in copy.** `flashAvailability()` returns
   `live` only when the catalog reports `availability: "available"`,
   `gateway_enabled` is true and a reviewed price exists. A missing catalog, a
   pending revision or a disabled provider all render a non-live state. The
   homepage banner only takes the green tone when that state is `live`.
2. **Display name and request id are separate.** Users read "DeepSeek V4.1
   Flash"; code samples and the catalog table use `deepseek-flash`. The Agent
   selector keeps sending the `default` routing sentinel while *labelling* it
   with the resolved platform model.
3. **An explicit model choice is never rewritten.** `agentModelLabel()` only
   maps the `default` sentinel and the ids that really resolve to the upgraded
   model; `gpt-5.6-luna` and historical messages keep their recorded model.
4. **The catalog list is generated, not curated.** The docs page renders every
   model the catalog returns, with a "no reviewed summary" note for models
   without editorial copy, so a newly enabled model cannot be invisible.
5. **Unverified capabilities are not advertised.** Context length, max output
   and price come from the catalog; when a field is absent the UI shows an
   explicit empty state rather than a number.
6. **Errors stay user-readable.** `describeChatFailure()` maps status codes and
   API error codes onto short localized sentences and keeps only a
   pattern-validated request id, so a stack trace, upstream host or key can
   never reach the browser.

Browser verification (`apps/web`, Next 14 dev server, screenshots captured):
Chinese and English homepages, the preview card and both entry links, the
catalog table and detail panel on `/zh/api` and `/en/api`, the Chat model badge
and error surface, mobile at 393px with no page-level horizontal overflow, and
keyboard focus plus accessible names on the new controls.

