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

* **Homepage product preview.** `apps/web/app/[locale]/page.tsx`,
  `apps/web/components/model-upgrade.tsx` and the `model-upgrade` message
  namespace are present in the working tree as unfinished work from another
  change. The preview component does not compile against the current
  `getMessageNamespace` typing (`Property 'stateLive' does not exist`), so it
  is **not** part of this release and is not deployed. The homepage advertises
  the upgrade through `landing.footerSlides`, and the API docs page
  (`/zh/api`, `/en/api`) shows the full model card, availability state and
  compatibility alias from the live catalog.
* **Kimi lane.** `kimi-k3-max` remains `pending` with no approved price
  revision, exactly as before this upgrade. `KIMI_AUTO_ROUTE=true` therefore
  degrades to DeepSeek until an operator approves the Moonshot price.
* **Peak/off-peak pricing.** The catalog stores off-peak USD prices. DeepSeek
  charges 2x during peak hours; the extra cost currently lands on the margin
  rather than on the customer.
* **Specialised models were not migrated.** Speech synthesis/recognition,
  embeddings and reranking do not run on DeepSeek; their providers and model
  ids are unchanged (see the audit table in the deployment report).

