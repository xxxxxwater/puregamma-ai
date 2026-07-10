# LLM Provider Architecture

PureGamma.ai uses a provider interface instead of hard-coding a model or vendor in agents.

```text
Report / Playbook Service
  -> ReportWriterAgent
  -> packages.agents.llm.provider_factory
  -> MockLLMProvider | OpenAIProvider | DeepSeekProvider
  -> LLMCallLog
```

## Interface

`packages/agents/llm/base.py` defines:

- `chat(messages, task_type, locale, user_id, db, response_format)`
- `complete(prompt, task_type, locale, user_id, db)`
- `structured_json(prompt, task_type, locale, user_id, db)`

Providers return `LLMResponse` from `packages/agents/llm/schemas.py`.

## Provider Selection

```text
LLM_PROVIDER=mock
LLM_PROVIDER=openai
LLM_PROVIDER=deepseek
```

- `mock` always works.
- `openai` requires `OPENAI_API_KEY`.
- `deepseek` requires `DEEPSEEK_API_KEY`.
- Missing real keys fall back to mock, but admin status reports the requested provider and fallback reason.

## Locale Policy

Agents pass `locale` into providers. DeepSeek uses a concise institutional English system message for `en` and a Simplified Chinese institutional research style for `zh`.

## Cost and Privacy

`LLMCallLog` records operational usage without full prompts. `packages/agents/llm/cost_tracker.py` redacts secret-like values and stores at most a 500-character prompt summary.

Cost estimates come from `config/llm_costs.yaml` and default to zero unless explicitly enabled for the provider.
