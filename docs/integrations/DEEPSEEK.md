# DeepSeek Provider
PureGamma AI uses a provider abstraction for LLM calls. DeepSeek is supported through the OpenAI-compatible chat completion API.
## Environment
```text
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_THINKING_MODE=disabled
DEEPSEEK_TIMEOUT_SECONDS=60
```
Keep `DEEPSEEK_API_KEY` out of documentation, tests, screenshots, and commits. Use local `.env` for development and a secret manager in production.
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
  "llm_model": "deepseek-v4-flash",
  "deepseek_configured": true
}
```
