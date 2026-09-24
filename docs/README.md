# PureGamma AI Documentation

This is the complete index of the PureGamma AI documentation set. It is written
for users, developers, administrators, operators, and enterprise customers.

Verified against `5d0cdea` (`main` = `refactor/harness-core-v2`). If a document
contradicts the code, the code wins — please fix the document.

- Project overview and quickstart: [../README.md](../README.md)
- Architectural decision behind the current refactor:
  [Harness Core V2](./architecture/HARNESS_CORE_V2.md)
- Documentation written in Chinese is marked **[zh]**; everything else is English.

## Start here

| If you are… | Read |
| --- | --- |
| New to the project | [Quickstart](./getting-started/QUICKSTART.md) → [Product Overview](./product/OVERVIEW.md) |
| A developer | [Architecture](./developer/ARCHITECTURE.md) → [Local Development](./getting-started/LOCAL_DEVELOPMENT.md) → [API Reference](./developer/API_REFERENCE.md) |
| An operator | [Deployment Overview](./deployment/DEPLOYMENT_OVERVIEW.md) → [Production Checklist](./deployment/PRODUCTION_CHECKLIST.md) → [Incident Runbook](./admin/INCIDENT_RUNBOOK.md) |
| Working on LIVE trading | [LIVE Architecture](./live-trading/ARCHITECTURE.md) → [Feature Flags](./live-trading/FEATURE_FLAGS.md) → [Status](./live-trading/STATUS.md) |
| Working on the Harness refactor | [Harness Core V2](./architecture/HARNESS_CORE_V2.md) → [Harness Research Architecture](./developer/HARNESS_RESEARCH_ARCHITECTURE.md) |

## Current implementation status

| Area | Status |
| --- | --- |
| Web dashboard (Next.js, en/zh) | Implemented |
| FastAPI backend (42 routers) | Implemented |
| Auth: Google OIDC, Apple, email/password, mobile sessions, mock login | Implemented |
| Reports, signals, playbooks | Implemented |
| Agent chat + Private Secretary | Implemented |
| Options research (Deribit / Polygon) | Implemented |
| Backtest Lab + executable strategy specs and compiler | Implemented |
| Research Runner sandbox | Implemented |
| Skills library (versioned declarative skills) | Implemented |
| Stripe Billing, Payment Links, credits, entitlements | Implemented |
| OpenAI-compatible API gateway + prepaid wallet | Implemented |
| LLM provider abstraction (DeepSeek default) | Implemented |
| Notifications: email, Telegram, Slack, APNs, iMessage relay | Implemented |
| Workers and scheduler | Implemented |
| Server-computed Portfolio NAV | Implemented; stale valuations are never fabricated |
| Plaid, IBKR, Hyperliquid connectors | Implemented behind credentials and freshness checks |
| Nautilus runtime (BACKTEST / PAPER / SHADOW) | Implemented as an isolated data plane |
| LIVE trading control plane | Implemented; every gate defaults OFF |
| Mobile capabilities API + memory + research runs | Implemented (`/api/mobile/capabilities`, `/api/memory/*`, `/api/research/runs*`) |
| iOS / Android apps | Code complete; App Store / Play release pending |
| PureGamma Harness plugin migration | In progress — see [Harness Core V2](./architecture/HARNESS_CORE_V2.md) |
| Redis Streams event pipeline and DLQ | Contract only, not built |
| Bloomberg enterprise import | Contract only |
| Tenant / workspace isolation | Not implemented (per-user isolation only) |

## Architecture and platform

- [Architecture](./developer/ARCHITECTURE.md) — workspace layout, runtime components, request flows, verified gaps
- [Harness Core V2 — Everything Is a Plugin](./architecture/HARNESS_CORE_V2.md)
- [DSH v0.1.7-rc.1 Agent / Skill / NAV PM upgrade design](./architecture/DSH_0_1_7_RC1_AGENT_SKILL_NAVPM_UPGRADE.md) **[zh]**
- [Target Architecture](./review/TARGET_ARCHITECTURE.md)
- [Agent Chat Architecture](./AGENT_CHAT_ARCHITECTURE.md)
- [Agent Platform Boundaries](./AGENT_PLATFORM_BOUNDARIES.md)
- [Agent Data Pipeline](./AGENT_DATA_PIPELINE.md)
- [Agent controlled online research](./AGENT_ONLINE_RESEARCH.md)
- [Agent Architecture](./developer/AGENT_ARCHITECTURE.md)
- [LLM Provider Architecture](./developer/LLM_PROVIDER_ARCHITECTURE.md)
- [Memory Architecture](./developer/MEMORY_ARCHITECTURE.md)
- [Harness Research Architecture](./developer/HARNESS_RESEARCH_ARCHITECTURE.md)
- [Automated Trading Foundation](./developer/AUTOMATED_TRADING_FOUNDATION.md)
- [Billing Architecture](./developer/BILLING_ARCHITECTURE.md)
- [Credit and Entitlements](./developer/CREDIT_AND_ENTITLEMENTS.md)
- [Database Schema](./developer/DATABASE_SCHEMA.md)
- [Skills Library](./SKILLS_LIBRARY.md)
- [AI API Gateway](./AI_API_GATEWAY.md)

## Getting started

- [Quickstart](./getting-started/QUICKSTART.md)
- [Local Development](./getting-started/LOCAL_DEVELOPMENT.md)
- [Environment Variables](./getting-started/ENVIRONMENT_VARIABLES.md)
- [Mock Mode](./getting-started/MOCK_MODE.md)
- [Docker Compose](./getting-started/DOCKER_COMPOSE.md)
- [Google Authentication](./GOOGLE_AUTH.md)
- [Deployment Checklist](./DEPLOYMENT_CHECKLIST.md)

## Product

- [Product Overview](./product/OVERVIEW.md)
- [PRD](./product/PRD.md)
- [MVP Scope Convergence](./product/MVP_SCOPE.md)
- [Pricing and Plans](./product/PRICING_AND_PLANS.md)
- [SaaS 套餐设计](./product/SAAS_PLANS.md) **[zh]**
- [Daily Brief](./product/DAILY_BRIEF.md)
- [每日 iMessage Brief 产品规格](./product/DAILY_IMESSAGE_BRIEF_SPEC.md) **[zh]**
- [Portfolio NAV](./product/PORTFOLIO_NAV.md)
- [Signals and Playbooks](./product/SIGNALS_AND_PLAYBOOKS.md)
- [METRICS](./product/METRICS.md)
- [BACKLOG](./product/BACKLOG.md)
- [PRODUCT_ROADMAP](./product/PRODUCT_ROADMAP.md)
- [LAUNCH_CHECKLIST](./product/LAUNCH_CHECKLIST.md)
- [USER_JOURNEY](./product/USER_JOURNEY.md)
- [USER_PERSONAS](./product/USER_PERSONAS.md)
- [V3 Commercial Design](./product/V3_COMMERCIAL_DESIGN.md)
- [V4 Deribit Options and Long Gamma](./product/V4_DERIBIT_LONG_GAMMA.md)

## Developer guides

- [API Reference](./developer/API_REFERENCE.md)
- [Adding a Data Provider](./developer/ADDING_DATA_PROVIDER.md)
- [Adding a Strategy](./developer/ADDING_STRATEGY.md)
- [Adding a Notification Provider](./developer/ADDING_NOTIFICATION_PROVIDER.md)

## Live trading

- [LIVE Trading + NAV 架构文档](./live-trading/ARCHITECTURE.md) **[zh]**
- [API 文档](./live-trading/API.md) **[zh]**
- [Feature Flag 文档](./live-trading/FEATURE_FLAGS.md) **[zh]**
- [风险与权限说明](./live-trading/RISK_AND_PERMISSIONS.md) **[zh]**
- [交付状态清单](./live-trading/STATUS.md) **[zh]**
- [生产部署说明](./live-trading/PRODUCTION_DEPLOYMENT.md) **[zh]**
- [变更文件清单](./live-trading/CHANGES.md) **[zh]**
- [上线架构方案](./live-trading/LIVE_LAUNCH_ARCHITECTURE.md) **[zh]**
- [上线 Runbook](./live-trading/LIVE_LAUNCH_RUNBOOK.md) **[zh]**
- [回滚方案](./live-trading/ROLLBACK.md) **[zh]**

## Mobile

- [统一移动端 API 契约](./mobile/MOBILE_API_CONTRACT.md) **[zh]**
- [Feature Flag 发布说明](./mobile/FEATURE_FLAGS_RELEASE_NOTES.md) **[zh]**
- [移动端升级安全检查清单](./mobile/SECURITY_CHECKLIST.md) **[zh]**
- [回滚方案](./mobile/ROLLBACK_PLAN.md) **[zh]**

## Trading runtime and quant

- [Trading Safety Contract](./trading/TRADING_SAFETY.md)
- [Runtime Operations](./trading/RUNTIME_OPERATIONS.md)
- [Phase 2: Public Market Paper Runtime](./trading/PHASE_2_PUBLIC_MARKET_RUNTIME.md)
- [Phase 3: Persistent Paper Portfolio Sync](./trading/PHASE_3_PAPER_PORTFOLIO_SYNC.md)
- [Backtesting Standard](./quant/BACKTESTING_STANDARD.md)
- [Backtesting Assumptions](./quant/BACKTESTING_ASSUMPTIONS.md)
- [Risk Model](./quant/RISK_MODEL.md)
- [Signal Confidence Framework](./quant/SIGNAL_CONFIDENCE_FRAMEWORK.md)
- [Strategy Research Framework](./quant/STRATEGY_RESEARCH_FRAMEWORK.md)
- [Strategy Catalog](./quant/STRATEGY_CATALOG.md)
- [Strategy Validation Checklist](./quant/STRATEGY_VALIDATION_CHECKLIST.md)
- [Agent Strategy Output Rules](./quant/AGENT_STRATEGY_OUTPUT_RULES.md)
- [Nautilus Research Guide](./quant/NAUTILUS_RESEARCH_GUIDE.md)
- [Nautilus Validation](./quant/NAUTILUS_VALIDATION.md)

### Built-in strategies

- [BTC Momentum Breakout](./quant/strategies/BTC_MOMENTUM_BREAKOUT.md)
- [ETH/BTC Rotation](./quant/strategies/ETH_BTC_ROTATION.md)
- [SOL/HYPE High Beta Rotation](./quant/strategies/SOL_HYPE_ROTATION.md)
- [HYPE Trend Following](./quant/strategies/HYPE_TREND_FOLLOWING.md)
- [MSTR Premium / BTC Proxy Trade](./quant/strategies/MSTR_BTC_PROXY.md)
- [STRC Event-Driven Credit Trade](./quant/strategies/STRC_EVENT_DRIVEN.md)
- [Basis Funding Arbitrage](./quant/strategies/BASIS_FUNDING_ARBITRAGE.md)

## Integrations

- [Stripe](./integrations/STRIPE.md)
- [Plaid](./integrations/PLAID.md)
- [DeepSeek Provider](./integrations/DEEPSEEK.md)
- [NautilusTrader Runtime](./integrations/NAUTILUS_TRADER.md)
- [Exchange Read-only Keys](./integrations/EXCHANGE_READONLY_KEYS.md)
- [On-chain Wallets](./integrations/ONCHAIN_WALLETS.md)
- [Telegram](./integrations/TELEGRAM.md)
- [Slack](./integrations/SLACK.md)
- [Email](./integrations/EMAIL.md)
- [iMessage Relay](./integrations/IMESSAGE_RELAY.md)
- [Photon iMessage Provider](./integrations/PHOTON_IMESSAGE.md)
- [Photon iMessage Rollout Runbook](./integrations/PHOTON_ROLLOUT_RUNBOOK.md)
- [Pocket Relay 手机访问 / cloudflared 隧道](./integrations/POCKET_MOBILE_ACCESS.md) **[zh]**
- [CoinDesk RSS](./integrations/COINDESK_RSS.md)
- [ChainCatcher 商业级快讯接入方案](./integrations/CHAINCATCHER_NEWSWIRE.md) **[zh]**
- [市场快讯灰度上线 Runbook](./integrations/CHAINCATCHER_GRAY_RELEASE_RUNBOOK.md) **[zh]**
- [X KOL](./integrations/X_KOL.md)
- [Bloomberg](./integrations/BLOOMBERG.md)
- [Data Sources](./DATA_SOURCES.md)
- [Public Data Sources](./PUBLIC_DATA_SOURCES.md)
- [Data License Policy](./DATA_LICENSE.md)

## Deployment and operations

- [Deployment Overview](./deployment/DEPLOYMENT_OVERVIEW.md)
- [Production Checklist](./deployment/PRODUCTION_CHECKLIST.md)
- [Commercial Operations](./deployment/COMMERCIAL_OPERATIONS.md)
- [Workers and Scheduler](./deployment/WORKERS_AND_SCHEDULER.md)
- [Database and Redis](./deployment/DATABASE_AND_REDIS.md)
- [Secrets Management](./deployment/SECRETS_MANAGEMENT.md)
- [Observability](./deployment/OBSERVABILITY.md)
- [Backup & Restore Runbook](./ops/BACKUP_RESTORE.md)
- [Harness Research Runbook](./operations/HARNESS_RUNBOOK.md)
- [Trading Mandate Runbook](./operations/TRADING_MANDATE_RUNBOOK.md)

## Administration

- [Admin Guide](./admin/ADMIN_GUIDE.md)
- [User Management](./admin/USER_MANAGEMENT.md)
- [Billing Operations](./admin/BILLING_OPERATIONS.md)
- [Data Source Monitoring](./admin/DATA_SOURCE_MONITORING.md)
- [Notification Deliveries](./admin/NOTIFICATION_DELIVERIES.md)
- [Incident Runbook](./admin/INCIDENT_RUNBOOK.md)

## Security and compliance

- [Security Overview](./security/SECURITY_OVERVIEW.md)
- [Secret Handling](./security/SECRET_HANDLING.md)
- [Data Privacy](./security/DATA_PRIVACY.md)
- [Tenant Isolation](./security/TENANT_ISOLATION.md)
- [Harness Threat Model](./security/HARNESS_THREAT_MODEL.md)
- [Memory Privacy and Retention](./security/MEMORY_PRIVACY_AND_RETENTION.md)
- [iMessage Security](./security/IMESSAGE_SECURITY.md)
- [Disclaimer Guide](./compliance/DISCLAIMER_GUIDE.md)
- [Investment Research Limits](./compliance/INVESTMENT_RESEARCH_LIMITS.md)
- [Backtest Disclosure](./compliance/BACKTEST_DISCLOSURE.md)
- [Portfolio NAV Disclosure](./compliance/PORTFOLIO_NAV_DISCLOSURE.md)

## Quality

- [Test Strategy](./qa/TEST_STRATEGY.md)
- [Release Checklist](./qa/RELEASE_CHECKLIST.md)
- [Bug Severity Guide](./qa/BUG_SEVERITY_GUIDE.md)

## Troubleshooting

- [Common Errors](./troubleshooting/COMMON_ERRORS.md)
- [Stripe Webhooks](./troubleshooting/STRIPE_WEBHOOKS.md)
- [iMessage Relay](./troubleshooting/IMESSAGE_RELAY.md)
- [Plaid Sync](./troubleshooting/PLAID_SYNC.md)
- [Portfolio NAV](./troubleshooting/PORTFOLIO_NAV.md)
- [Worker Queue](./troubleshooting/WORKER_QUEUE.md)
- [Nautilus](./troubleshooting/NAUTILUS.md)

## User guide (GitBook)

Chinese:

- [使用手册](./gitbook/README.md) / [快速上手](./gitbook/getting-started.md) / [常见问题](./gitbook/faq.md) / [产品路线图](./gitbook/roadmap.md)
- [订阅与 Credits](./gitbook/billing-credits.md) / [账户与安全](./gitbook/account-security.md) / [移动应用](./gitbook/mobile-apps.md)
- [API 中转站](./gitbook/api-gateway.md)
- Features: [功能指南](./gitbook/features/README.md) / [Agent 对话](./gitbook/features/agent-chat.md) / [回测实验室](./gitbook/features/backtest-lab.md) / [仪表盘与每日简报](./gitbook/features/dashboard-reports.md) / [通知与 iMessage](./gitbook/features/notifications.md) / [期权研究](./gitbook/features/options-research.md) / [组合与连接](./gitbook/features/portfolio-nav.md) / [私人秘书](./gitbook/features/secretary-voice.md)

English:

- [User Guide](./gitbook/english/README.md) / [Getting Started](./gitbook/english/getting-started.md) / [Feature Guide](./gitbook/english/features.md) / [FAQ & Roadmap](./gitbook/english/faq-roadmap.md) / [Billing & Credits](./gitbook/english/billing-credits.md)
- [API Gateway](./gitbook/api-gateway-en.md)
- [i18n Glossary](./i18n/GLOSSARY.md) / [Web glossary](./../apps/web/messages/GLOSSARY.md)

## Point-in-time records (historical)

These documents record a specific moment. They are useful as evidence and
context, but they are **not** the current state of the system — check the
[implementation status](#current-implementation-status) instead.

### Release records

- [2.2 预部署 — 变更清单](./release/2.2/CHANGELIST.md) **[zh]**
- [2.2 预部署 — 发布结论](./release/2.2/DEPLOYMENT_VERDICT.md) **[zh]**
- [2.2 预部署 — 环境变量清单](./release/2.2/ENV_VARIABLES.md) **[zh]**
- [2.2 预部署 — 风险清单](./release/2.2/RISKS.md) **[zh]**
- [2.2 预部署 — 回滚步骤](./release/2.2/ROLLBACK.md) **[zh]**
- [2.2 预部署 — 冒烟记录](./release/2.2/SMOKE_RECORD.md) **[zh]**
- [2.2 预部署 — 测试命令与结果](./release/2.2/TEST_RESULTS.md) **[zh]**
- [2.2 预部署 — 未完成接口清单](./release/2.2/UNIMPLEMENTED_ENDPOINTS.md) **[zh]**
- [MVP Upgrade — 2026-07-24](./release/MVP_20260724_UPGRADE.md)
- [DeepSeek V4.1 Flash Upgrade](./models/DEEPSEEK_V41_FLASH_UPGRADE.md)
- [移动端变更文件清单与验证结果](./mobile/CHANGELIST_AND_VERIFICATION.md) **[zh]**
- [Git 工作区拆分与发布卫生](./mobile/GIT_HYGIENE.md) **[zh]**
- [Admin session handoff (credential-free)](./verification/ADMIN_SESSION_HANDOFF.md)

### Audits and reviews

- [PureGamma AI Implementation Audit](./PROJECT_IMPLEMENTATION_AUDIT.md)
- [Implementation Report](./IMPLEMENTATION_REPORT.md)
- [V5 Initial Launch Review](./V5_INITIAL_LAUNCH_REVIEW.md)
- [Commercial Closeout Round 2](./COMMERCIAL_CLOSEOUT_ROUND2.md)
- [Portfolio NAV and Autopilot Production Review](./PORTFOLIO_AUTOPILOT_PRODUCTION_REVIEW.md)
- [Audit Before Nautilus Runtime Implementation](./AUDIT_BEFORE_IMPLEMENTATION.md)
- [Current implementation audit](./review/CURRENT_IMPLEMENTATION_AUDIT.md)
- [Production blockers](./review/PRODUCTION_BLOCKERS.md)
- [Mock and fallback inventory](./review/MOCK_AND_FALLBACK_INVENTORY.md)
- [Credits and metering audit](./review/CREDIT_AND_METERING_AUDIT.md)
- [Secret and configuration audit](./review/SECRET_AND_CONFIGURATION_AUDIT.md)
- [Implementation phases](./review/IMPLEMENTATION_PHASES.md)
- [Production Baseline implementation report](./review/FINAL_IMPLEMENTATION_REPORT.md)
- [PureGamma iOS — Commercial-grade review](./review/IOS_COMMERCIAL_GRADE_REVIEW.md)
- [ChainCatcher 新闻流整合评审](./review/CHAINCATCHER_NEWS_FEED_REVIEW.md) **[zh]**
- [NautilusTrader Phase 0 Spike Report](./trading/NAUTILUS_TRADER_SPIKE.md)

### LIVE trading verification and launch artefacts

- [首单验证报告(模板与证据清单)](./live-trading/FIRST_ORDER_VERIFICATION.md) **[zh]**

### Frontend audits

- [UI Theme Audit](./frontend/UI_THEME_AUDIT.md)
- [UI Density Audit](./frontend/UI_DENSITY_AUDIT.md)
- [Hardcoded Colour Audit](./frontend/HARDCODED_COLOR_AUDIT.md)

### Prompts and archived plans

- [第五轮 UI / UX 升级执行提示词](./frontend/ROUND5_PROMPT.md) **[zh]**
- [UIUX Round 5 prompt — **archived, do not use as an execution basis**](./UIUX_ROUND5_PROMPT.md) **[zh]**
- [提示词(前端工程师) — 实盘 LIVE 控制台 UI](./live-trading/PROMPT_FRONTEND_LIVE_UI.md) **[zh]**
- [提示词(MVP/后端工程师) — 实盘 LIVE 开启与部署](./live-trading/PROMPT_MVP_LIVE_BACKEND.md) **[zh]**

## Recommended reading paths

**New user**

1. [Product Overview](./product/OVERVIEW.md)
2. [Daily Brief](./product/DAILY_BRIEF.md)
3. [Portfolio NAV](./product/PORTFOLIO_NAV.md)
4. [Pricing and Plans](./product/PRICING_AND_PLANS.md)

**Developer**

1. [Quickstart](./getting-started/QUICKSTART.md)
2. [Local Development](./getting-started/LOCAL_DEVELOPMENT.md)
3. [Architecture](./developer/ARCHITECTURE.md)
4. [API Reference](./developer/API_REFERENCE.md)

**Operator or administrator**

1. [Deployment Overview](./deployment/DEPLOYMENT_OVERVIEW.md)
2. [Production Checklist](./deployment/PRODUCTION_CHECKLIST.md)
3. [Admin Guide](./admin/ADMIN_GUIDE.md)
4. [Incident Runbook](./admin/INCIDENT_RUNBOOK.md)

**Enterprise customer**

1. [Security Overview](./security/SECURITY_OVERVIEW.md)
2. [Data Privacy](./security/DATA_PRIVACY.md)
3. [Tenant Isolation](./security/TENANT_ISOLATION.md)
4. [Investment Research Limits](./compliance/INVESTMENT_RESEARCH_LIMITS.md)
