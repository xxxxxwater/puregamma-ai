import type { PureGammaCapabilityDescriptor } from './contracts.js'

/**
 * Target plugin ownership map for the PureGamma Harness refactor.
 *
 * `legacyOwners` are source locations to extract/wrap; new code must not import
 * them as architectural dependencies from the Harness side.
 */
export const PUREGAMMA_CAPABILITIES: readonly PureGammaCapabilityDescriptor[] = [
  {
    id: 'auth',
    packageName: '@puregamma/dsh-auth',
    plane: 'dual',
    risk: 'stateful',
    services: ['pgAuth', 'pgEntitlements'],
    tools: [],
    ui: ['settings.account', 'conversation.auth-state'],
    legacyOwners: ['apps/api/routers/auth*', 'apps/web/middleware.ts'],
  },
  {
    id: 'market-data',
    packageName: '@puregamma/dsh-market-data',
    plane: 'host',
    risk: 'read-only',
    services: ['pgMarketData', 'pgNews', 'pgProviderHealth'],
    tools: ['market_snapshot', 'market_news', 'market_provider_health'],
    ui: ['tool.market-snapshot', 'tool.market-news'],
    legacyOwners: ['packages/data', 'apps/api/routers/*market*'],
  },
  {
    id: 'research',
    packageName: '@puregamma/dsh-research',
    plane: 'dual',
    risk: 'read-only',
    services: ['pgResearch'],
    tools: ['research_run', 'research_status', 'research_artifact'],
    ui: ['tool.research-run', 'resource.research-artifact'],
    legacyOwners: ['packages/agents', 'packages/harness', 'apps/web/plugins/builtin/research'],
  },
  {
    id: 'portfolio',
    packageName: '@puregamma/dsh-portfolio',
    plane: 'dual',
    risk: 'read-only',
    services: ['pgPortfolio', 'pgNav'],
    tools: ['portfolio_snapshot', 'portfolio_positions', 'portfolio_nav'],
    ui: ['tool.portfolio', 'resource.portfolio'],
    legacyOwners: ['packages/portfolio', 'apps/web/plugins/builtin/portfolio'],
  },
  {
    id: 'options',
    packageName: '@puregamma/dsh-options',
    plane: 'dual',
    risk: 'read-only',
    services: ['pgOptions'],
    tools: ['options_chain', 'options_surface', 'gamma_candidates'],
    ui: ['tool.options-chain', 'tool.options-surface'],
    legacyOwners: ['packages/options', 'apps/web/plugins/builtin/options'],
  },
  {
    id: 'backtest',
    packageName: '@puregamma/dsh-backtest',
    plane: 'dual',
    risk: 'stateful',
    services: ['pgBacktest'],
    tools: ['backtest_compile', 'backtest_run', 'backtest_result'],
    ui: ['tool.backtest', 'resource.backtest-artifact'],
    legacyOwners: ['packages/backtest'],
  },
  {
    id: 'memory',
    packageName: '@puregamma/dsh-memory',
    plane: 'host',
    risk: 'stateful',
    services: ['pgMemory'],
    tools: ['memory_search', 'memory_propose', 'memory_forget'],
    ui: ['settings.memory'],
    legacyOwners: ['packages/memory'],
  },
  {
    id: 'trading',
    packageName: '@puregamma/dsh-trading',
    plane: 'dual',
    risk: 'money-movement',
    services: ['pgExecution', 'pgRisk', 'pgReconciliation', 'pgLedger'],
    tools: ['trade_preview', 'trade_submit', 'trade_cancel', 'trading_status'],
    ui: ['tool.trade-preview', 'tool.order', 'resource.trading-status'],
    legacyOwners: ['packages/trading', 'packages/live_trading', 'packages/nautilus', 'services/nautilus-runtime', 'apps/web/plugins/builtin/trading'],
  },
  {
    id: 'notifications',
    packageName: '@puregamma/dsh-notifications',
    plane: 'host',
    risk: 'stateful',
    services: ['pgNotifications'],
    tools: ['notification_send', 'notification_channels'],
    ui: ['settings.notifications'],
    legacyOwners: ['packages/notifications'],
  },
  {
    id: 'billing',
    packageName: '@puregamma/dsh-billing',
    plane: 'dual',
    risk: 'stateful',
    services: ['pgBilling', 'pgEntitlements'],
    tools: ['billing_status', 'usage_status'],
    ui: ['settings.billing', 'resource.usage'],
    legacyOwners: ['packages/billing', 'apps/api/routers/*billing*'],
  },
  {
    id: 'api-gateway',
    packageName: '@puregamma/dsh-api-gateway',
    plane: 'host',
    risk: 'stateful',
    services: ['pgModelGateway'],
    tools: ['gateway_usage', 'gateway_keys'],
    ui: ['settings.api-gateway', 'resource.gateway-usage'],
    legacyOwners: ['packages/gateway'],
  },
  {
    id: 'admin',
    packageName: '@puregamma/dsh-admin',
    plane: 'dual',
    risk: 'stateful',
    services: ['pgAdmin'],
    tools: ['admin_health', 'admin_plugin_inventory'],
    ui: ['settings.admin', 'resource.admin-health'],
    legacyOwners: ['apps/web/app/*/admin', 'apps/api/routers/admin*'],
  },
] as const

export function capabilityById(id: PureGammaCapabilityDescriptor['id']) {
  return PUREGAMMA_CAPABILITIES.find(capability => capability.id === id)
}
