# Production Baseline implementation report
## This delivery
* **Implemented:** production environment validator, fail-fast Compose, Docker CLI compatibility, production smoke script, liveness/readiness endpoints, non-root images, authenticated SecretStore, capability registry, unified Credits metering, persisted reservation/settlement/refund state, append-only ledger, automation budgets, reward ledger, Agent/Luna provider-usage settlement, report/notification/backtest/strategy/signal/preview metering, frontend server Quote and actual-cost display, and production frontend fallback boundary.
* **Partially implemented:** several hidden P2+ pages still need complete `unavailable/stale/partial` visual states; reward trigger workflows beyond portfolio onboarding/admin grant are policy-ready but not all exposed as product actions.
* **Hidden compatibility routes:** `/internal/capabilities` and `/internal/portfolio-ai/snapshot` are admin + internal-secret protected and disabled by default. Risk, realtime and Trading MCP expose status contracts only; they return `NOT_IMPLEMENTED` until their deterministic backends exist.
* **Hidden deterministic Risk Engine:** `packages/risk/engine.py` now evaluates fresh Portfolio Context data, concentration, gross exposure and configured stress scenarios without an LLM. It blocks stale/not-connected data and is not a pre-trade approval gate yet.
* **Mock:** Mock Agent, mock market provider, mock notifications and Nautilus mock backtests remain test/local capabilities and are not production evidence.
* **Placeholder:** full Redis Streams pipeline, complete deterministic Risk Copilot/pre-trade gate, Global Agent artifacts, Trading MCP and complete Portfolio fact layer.
* **External credential required:** Postgres, Redis, Stripe, OpenAI/DeepSeek, OAuth/Portfolio connectors, notification providers and Nautilus runtime secrets.
* **Production ready:** P1 metering code and the existing Auth/Stripe webhook/PAPER-SHADOW safety boundaries passed local production Compose smoke; real credentials, DNS/TLS, backup/restore and target-host smoke are still required before users.
* **Blocked:** unrestricted live trading, withdrawal and transfer remain disabled by policy.
* **Known risk:** real provider invoice reconciliation and calendar-boundary budget rollover need staging observation; P2+ Portfolio/Risk/Realtime/MCP capabilities remain hidden and are not production claims.
## Files and APIs
* Configuration: `apps/api/config.py`, `.env.example`, `scripts/validate-production-env.py`.
* Deployment: `docker-compose.production.yml`, `scripts/resolve-docker-cli.sh`, `scripts/production-smoke.sh`.
* Metering: `packages/billing/metering.py`, `apps/api/services/credit_service.py`, `apps/api/routers/billing.py`.
* Secrets/capabilities: `packages/config/secret_store.py`, `packages/capabilities/registry.py`.
* Frontend boundary: `apps/web/lib/api.ts`, `apps/web/components/agent-chat.tsx`, `apps/web/Dockerfile`.
* User API: `POST /billing/quote`, `GET /billing/ledger`, `GET/PUT /billing/budget`, `GET /billing/rewards`.
* Server-only boundary: reservation, settlement, refund and actual usage are not exposed to ordinary users.
* Migrations: `0006_credit_state_machine`, `0007_credit_ledger_immutability`.
## Current defaults
* Default Agent model is unchanged.
* GPT-5.6 Luna remains optional and plan-gated; its flag is controlled by `OPENAI_LUNA_ENABLED` and its real API key is server-side only.
* Mock providers are not allowed as healthy production capabilities.
* LIVE, withdrawal and transfer remain disabled.
* Portfolio/Risk/Realtime/MCP are not claimed complete in this delivery.
## Evidence
Passed on macOS with the repository `.venv` and Docker Desktop 28.4.0:
* full `.venv/bin/pytest -q` suite (exit 0; existing P2+ contract xfails remain explicit);
* frontend typecheck, ESLint and Next.js production build (89 pages, including `/health`);
* production environment validation and Compose `config --quiet` with redacted dummy values;
* Docker production builds for API, Web and Nautilus Runtime;
* Web runtime image converted to Next.js standalone output (about 737 MB down to 223 MB in the local build) and verified healthy as non-root;
* clean PostgreSQL 16 migration from baseline through `0007_credit_ledger_immutability` and ORM schema check;
* live smoke start of Postgres, Redis, Runtime, API, Worker, Scheduler and Web with healthy API/Web/Runtime dependencies;
* raw PostgreSQL and SQLite UPDATE probes rejected by the append-only ledger trigger;
* Caddy configuration validation;
* `git diff --check`.
The system Anaconda pytest command has an unrelated global `web3`/`eth_typing` plugin conflict; the repository `.venv/bin/pytest` is the validated project runner.
