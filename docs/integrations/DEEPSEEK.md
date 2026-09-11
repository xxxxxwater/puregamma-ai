# DeepSeek Provider
PureGamma AI uses a provider abstraction for LLM calls. DeepSeek is supported through the OpenAI-compatible chat completion API.

The platform default is **DeepSeek V4.1 Flash** (released 2026-09-10). Its official API model name is `deepseek-flash`; "DeepSeek V4.1 Flash" is the display name only. Never construct a model id from the display name — `deepseek-v4.1-flash` does not exist.

## Environment
```text
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_THINKING_MODE=disabled
DEEPSEEK_REASONING_EFFORT=high
DEEPSEEK_TIMEOUT_SECONDS=60
```
Keep `DEEPSEEK_API_KEY` out of documentation, tests, screenshots, and commits. Use local `.env` for development and a secret manager in production.
## Model identity
- `deepseek-flash` is the model to configure. `settings.deepseek_effective_model` normalises any retired name to the model that actually serves it.
- The retired names `deepseek-v4-flash`, `deepseek-v4-flash-0731` and `deepseek-v4-flash-vision-exp` still resolve to V4.1 Flash upstream. PureGamma records them as `deepseek-flash` so logs, ledgers and metrics name the model that really ran.
- `deepseek-v4-pro` is **not** rewritten. DeepSeek announced that from 2026-09-14 12:00 Beijing time this id is routed to V4.1 Flash; until then it is a different model, so rewriting it would falsify attribution.
- A model the caller explicitly names is never swapped for DeepSeek.
## Thinking mode
- V4.1 Flash enables thinking with `effort=high` **by default**. In that mode DeepSeek ignores `temperature`, `presence_penalty` and `frequency_penalty`, bills reasoning tokens as output, and returns the chain of thought separately as `reasoning_content`.
- Platform paths (Agent chat, streaming, daily reports) disable it with `{"thinking": {"type": "disabled"}}`, which is why `DEEPSEEK_THINKING_MODE=disabled` is the production default.
- When thinking is enabled, `temperature` and `max_tokens` are not sent: a reasoning budget placed at the cap can consume the whole response and return empty `content`.
- Requests that carry `tools` must return each prior turn's `reasoning_content` or DeepSeek answers `400`. Thinking is therefore never enabled on a platform path that follows up on a tool call.
## Runtime Behavior
- `packages/agents/llm/provider_factory.py` selects `mock`, `openai`, or `deepseek`.
- Missing `DEEPSEEK_API_KEY` automatically falls back to `MockLLMProvider`.
- Report and playbook generation call the provider through the shared abstraction.
- The provider uses bounded timeout, retry, and exponential backoff.
- Structured JSON calls use `response_format={"type":"json_object"}` when requested.
## Logging
LLM calls are logged to `LLMCallLog` with:
- provider
- model
- task type
- locale
- prompt summary
- token counts
- estimated cost
- status
- error message
The log stores a redacted prompt summary only. API keys, secret-like fields, tokens, passwords, and phone-like values are replaced with `[REDACTED]`.
Admin endpoints:
```text
GET /admin/llm-status
GET /admin/llm-calls
GET /admin/llm-cost-summary
GET /admin/system-status
```
## Cost Configuration
Costs are configured in `config/llm_costs.yaml`. The default values are conservative placeholders. Update the rates from the active provider contract before using the cost dashboard for finance reporting.
The credit system includes:
- `deepseek_report_generation = 10`
- `deepseek_playbook_generation = 30`
These are high-cost action names for entitlement and policy wiring. Current report generation keeps the existing report/playbook credit charge path and logs provider usage separately.
## Local Smoke Test
```bash
python3 -m pytest tests/unit/test_llm_provider.py
curl http://localhost:8000/health
```
Expected health fields include:
```json
{
  "llm_provider": "deepseek",
  "llm_model": "deepseek-flash",
  "deepseek_configured": true
}
```
