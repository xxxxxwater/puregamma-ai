import type { PureGammaCapabilityDescriptor } from './contracts.js'

/**
 * Target ownership map for PureGamma Harness.
 *
 * `legacyOwners` are migration inputs only. Harness plugins must consume stable
 * Service Definitions and must never make legacy apps/packages/services a
 * permanent architectural dependency.
 */
export const PUREGAMMA_CAPABILITIES: readonly PureGammaCapabilityDescriptor[] = [
  {
    id: 'web-presence', packageName: '@puregamma/dsh-web-presence', plane: 'dual', risk: 'read-only',
    services: ['pgPublicContent'], tools: [],
    ui: ['public.landing', 'public.docs', 'public.pricing', 'public.privacy', 'public.terms'],
    legacyOwners: ['apps/web/app/[locale]/page.tsx', 'apps/web/app/[locale]/docs/page.tsx', 'apps/web/app/privacy/page.tsx', 'apps/web/app/terms/page.tsx'],
  },
  {
    id: 'auth', packageName: '@puregamma/dsh-auth', plane: 'dual', risk: 'stateful',
    services: ['pgAuth'], tools: ['auth_status'],
    ui: ['settings.account', 'conversation.auth-state', 'resource.account-export'],
    legacyOwners: ['apps/api/routers/auth.py', 'apps/api/routers/google_auth.py', 'apps/api/routers/apple_auth.py', 'apps/api/routers/email_auth.py', 'apps/api/routers/mobile_auth.py', 'apps/web/middleware.ts'],
  },
  {
    id: 'agent-chat', packageName: '@puregamma/dsh-agent-chat', plane: 'dual', risk: 'stateful',
    services: ['pgConversationPolicy', 'pgAgentQuota'], tools: [],
    ui: ['conversation.root', 'conversation.citations', 'conversation.tool-calls'],
    legacyOwners: ['apps/api/routers/*agent*', 'packages/agents', 'docs/AGENT_CHAT_ARCHITECTURE.md'],
  },
  {
    id: 'market-data', packageName: '@puregamma/dsh-market-data', plane: 'host', risk: 'read-only',
    services: ['pgMarketData', 'pgNews', 'pgProviderHealth'],
    tools: ['market_snapshot', 'market_news', 'market_provider_health'],
    ui: ['tool.market-snapshot', 'tool.market-news'],
    legacyOwners: ['packages/data', 'apps/api/routers/*market*', 'docs/PUBLIC_DATA_SOURCES.md'],
  },
  {
    id: 'data-sources', packageName: '@puregamma/dsh-data-sources', plane: 'dual', risk: 'stateful',
    services: ['pgDataSources', 'pgSourceEntitlements'], tools: ['data_source_status', 'data_source_catalog'],
    ui: ['settings.data-sources', 'resource.data-source-health'],
    legacyOwners: ['packages/data', 'apps/api/routers/admin*', 'apps/web/app/*/admin*'],
  },
  {
    id: 'research', packageName: '@puregamma/dsh-research', plane: 'dual', risk: 'read-only',
    services: ['pgResearch'],
    tools: ['research_today', 'research_overnight', 'research_portfolio_impact', 'research_upcoming_events', 'research_opportunities', 'research_alerts'],
    ui: ['tool.research-run', 'resource.research-artifact'],
    legacyOwners: ['packages/agents', 'packages/harness', 'apps/web/plugins/builtin/research', 'docs/developer/HARNESS_RESEARCH_ARCHITECTURE.md'],
  },
  {
    id: 'research-runner', packageName: '@puregamma/dsh-research-runner', plane: 'host', risk: 'stateful',
    services: ['pgResearchSandbox'], tools: ['research_code_run', 'research_code_status', 'research_code_cancel'],
    ui: ['resource.research-run', 'resource.research-figure'],
    legacyOwners: ['packages/research_runner', 'apps/api/routers/research_runner.py', 'apps/api/services/research_runner_service.py', 'services/*runner*'],
  },
  {
    id: 'secretary', packageName: '@puregamma/dsh-secretary', plane: 'dual', risk: 'stateful',
    services: ['pgSecretary'], tools: ['secretary_status'],
    ui: ['conversation.secretary-mode', 'settings.secretary', 'resource.secretary-voice'],
    legacyOwners: ['apps/api/routers/secretary.py', 'apps/web/plugins/builtin/secretary', 'packages/agents', 'packages/notifications'],
  },
  {
    id: 'skills', packageName: '@puregamma/dsh-skills', plane: 'host', risk: 'stateful',
    services: ['pgSkills'], tools: ['skill_catalog', 'skill_run', 'skill_run_status'],
    ui: ['settings.skills', 'resource.skill-run'],
    legacyOwners: ['apps/api/routers/skills.py', 'apps/api/services/skill_service.py', 'apps/api/services/skill_workflow_service.py', 'packages/skills', 'docs/SKILLS_LIBRARY.md'],
  },
  {
    id: 'portfolio', packageName: '@puregamma/dsh-portfolio', plane: 'dual', risk: 'read-only',
    services: ['pgPortfolio', 'pgNav'], tools: ['portfolio_snapshot', 'portfolio_positions', 'portfolio_nav'],
    ui: ['tool.portfolio', 'resource.portfolio'],
    legacyOwners: ['packages/portfolio', 'apps/web/plugins/builtin/portfolio', 'apps/api/services/portfolio_service.py'],
  },
  {
    id: 'portfolio-autopilot', packageName: '@puregamma/dsh-portfolio-autopilot', plane: 'host', risk: 'stateful',
    services: ['pgPortfolioAutopilot'], tools: ['portfolio_review', 'portfolio_review_schedule'],
    ui: ['settings.portfolio-autopilot', 'resource.portfolio-review'],
    legacyOwners: ['packages/portfolio', 'packages/notifications', 'apps/api/services/*portfolio*'],
  },
  {
    // The private Binance PM account is deliberately NOT part of 'portfolio':
    // it is never merged into a user's aggregate NAV, only an allowlisted
    // subset may read it, and it exposes no model tool at all.
    id: 'pm-nav', packageName: '@puregamma/dsh-pm-nav', plane: 'dual', risk: 'read-only',
    services: ['pgPmNav'], tools: [],
    ui: ['settings.pm-nav'],
    legacyOwners: ['apps/api/services/pm_riskbot_service.py', 'apps/api/routers/portfolio.py', 'apps/web/components/pm-account-panel.tsx'],
  },
  {
    id: 'options', packageName: '@puregamma/dsh-options', plane: 'dual', risk: 'read-only',
    services: ['pgOptions'], tools: ['options_chain', 'options_long_gamma', 'options_surface', 'options_surface_tickers', 'options_earnings_gamma'],
    ui: ['tool.options-chain', 'tool.options-surface'],
    legacyOwners: ['packages/options', 'apps/web/plugins/builtin/options'],
  },
  {
    id: 'backtest', packageName: '@puregamma/dsh-backtest', plane: 'dual', risk: 'stateful',
    services: ['pgBacktest'],
    tools: ['backtest_status', 'backtest_compile', 'backtest_run', 'backtest_runs', 'backtest_result', 'backtest_cancel', 'backtest_export', 'backtest_save_strategy', 'backtest_refresh_data'],
    ui: ['tool.backtest', 'resource.backtest-artifact'],
    legacyOwners: ['packages/backtest', 'apps/api/routers/backtest*', 'apps/api/services/*backtest*'],
  },
  {
    id: 'memory', packageName: '@puregamma/dsh-memory', plane: 'dual', risk: 'stateful',
    services: ['pgMemory'], tools: ['memory_settings', 'memory_items', 'memory_proposals', 'memory_export_descriptor'],
    ui: ['settings.memory', 'resource.memory-export'],
    legacyOwners: ['packages/memory', 'apps/api/routers/memory.py', 'docs/developer/MEMORY_ARCHITECTURE.md'],
  },
  {
    id: 'trading', packageName: '@puregamma/dsh-trading', plane: 'dual', risk: 'money-movement',
    services: ['pgExecution', 'pgRisk', 'pgReconciliation', 'pgLedger', 'pgKillSwitch'],
    tools: ['trade_preview', 'trade_submit', 'trade_cancel', 'trading_status'],
    ui: ['tool.trade-preview', 'tool.order', 'resource.trading-status'],
    legacyOwners: ['packages/trading', 'packages/live_trading', 'apps/web/plugins/builtin/trading'],
  },
  {
    id: 'trading-mandates', packageName: '@puregamma/dsh-trading-mandates', plane: 'dual', risk: 'money-movement',
    services: ['pgTradingMandates', 'pgTradingApproval'], tools: ['mandate_status', 'mandate_pause', 'mandate_resume'],
    ui: ['settings.trading-mandates', 'resource.trading-safety'],
    legacyOwners: ['packages/trading', 'packages/live_trading', 'docs/developer/AUTOMATED_TRADING_FOUNDATION.md'],
  },
  {
    id: 'nautilus-runtime', packageName: '@puregamma/dsh-nautilus-runtime', plane: 'host', risk: 'money-movement',
    services: ['pgNautilusRuntime'], tools: ['nautilus_runtime_status'], ui: ['resource.nautilus-runtime'],
    legacyOwners: ['packages/nautilus', 'services/nautilus-runtime'],
  },
  {
    id: 'pg-tsy-runtime', packageName: '@puregamma/dsh-pg-tsy-runtime', plane: 'host', risk: 'money-movement',
    services: ['pgTsyRuntime'], tools: ['quant_runtime_status'], ui: ['resource.quant-runtime'],
    legacyOwners: ['vendor/pg-tsy-core-bootstrap'],
  },
  {
    id: 'notifications', packageName: '@puregamma/dsh-notifications', plane: 'dual', risk: 'stateful',
    services: ['pgNotifications'], tools: ['notification_channels', 'notification_daily_brief', 'notification_deliveries'],
    ui: ['settings.notifications', 'resource.notification-deliveries'],
    legacyOwners: ['apps/api/routers/notifications.py', 'apps/api/services/notification_service.py', 'apps/api/services/daily_push_service.py', 'packages/notifications'],
  },
  {
    id: 'billing', packageName: '@puregamma/dsh-billing', plane: 'dual', risk: 'stateful',
    services: ['pgBilling'], tools: ['billing_status', 'billing_quote', 'billing_budget'],
    ui: ['settings.billing', 'resource.usage', 'resource.entitlements'],
    legacyOwners: ['apps/api/routers/billing.py', 'apps/api/services/billing_service.py', 'apps/api/services/credit_service.py', 'apps/api/services/entitlement_service.py', 'packages/billing'],
  },
  {
    id: 'api-gateway', packageName: '@puregamma/dsh-api-gateway', plane: 'dual', risk: 'stateful',
    services: ['pgModelGateway', 'pgModelCatalog', 'pgUsageMeter'], tools: ['gateway_usage', 'gateway_keys', 'gateway_models'],
    ui: ['settings.api-gateway', 'resource.gateway-usage'],
    legacyOwners: ['packages/gateway', 'apps/api/routers/gateway.py', 'docs/AI_API_GATEWAY.md'],
  },
  {
    id: 'mobile-api', packageName: '@puregamma/dsh-mobile-api', plane: 'host', risk: 'stateful',
    services: ['pgMobileCapabilities', 'pgDeepLinks', 'pgPushRouting'], tools: [], ui: [],
    legacyOwners: ['apps/ios', 'apps/android', 'docs/mobile/MOBILE_API_CONTRACT.md'],
  },
  {
    // Distinct from 'mobile-api' (the native iOS/Android clients): this is the
    // self-hosted pocket-relay access surface. Reads are open to signed-in
    // users; tunnel and PIN changes are admin-only.
    id: 'mobile-access', packageName: '@puregamma/dsh-mobile-access', plane: 'host', risk: 'stateful',
    services: ['pgMobileAccess'], tools: [], ui: [],
    legacyOwners: ['apps/api/routers/mobile_access.py', 'apps/web/app/[locale]/mobile-access/page.tsx', 'apps/web/components/mobile-access-panel.tsx', 'apps/pocket-relay'],
  },
  {
    id: 'admin', packageName: '@puregamma/dsh-admin', plane: 'dual', risk: 'stateful',
    services: ['pgAdmin', 'pgPluginInventory'], tools: ['admin_health', 'admin_plugin_inventory'],
    ui: ['settings.admin', 'resource.admin-health'],
    legacyOwners: ['apps/web/app/*/admin*', 'apps/api/routers/admin*'],
  },
] as const

export function capabilityById(id: PureGammaCapabilityDescriptor['id']) {
  return PUREGAMMA_CAPABILITIES.find(capability => capability.id === id)
}
