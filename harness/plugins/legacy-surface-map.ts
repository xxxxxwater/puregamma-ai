import type { PureGammaCapabilityId } from './contracts.js'

/**
 * Legacy PureGamma.ai API/UI surfaces and their mandatory PureGamma Harness
 * plugin owners. This is an anti-omission migration ledger: a legacy surface is
 * deleted only after its target plugin passes parity and lifecycle tests.
 */
export interface LegacySurfaceMigration {
  surface: string
  target: PureGammaCapabilityId
  disposition: 'service' | 'provider' | 'tool' | 'worker' | 'client' | 'compatibility-only'
  note: string
}

export const LEGACY_SURFACE_MIGRATIONS: readonly LegacySurfaceMigration[] = [
  { surface: 'apps/api/routers/admin.py', target: 'admin', disposition: 'service', note: 'Admin operations and plugin inventory.' },
  { surface: 'apps/api/routers/agent.py', target: 'agent-chat', disposition: 'service', note: 'Persistent conversation/streaming/quota policy moves behind Harness session + agent plugins.' },
  { surface: 'apps/api/routers/apple_auth.py', target: 'auth', disposition: 'provider', note: 'Apple identity provider.' },
  { surface: 'apps/api/routers/auth.py', target: 'auth', disposition: 'service', note: 'Account/session/entitlement seam.' },
  { surface: 'apps/api/routers/email_auth.py', target: 'auth', disposition: 'provider', note: 'Email/password identity provider.' },
  { surface: 'apps/api/routers/google_auth.py', target: 'auth', disposition: 'provider', note: 'Google OIDC provider.' },
  { surface: 'apps/api/routers/mobile_auth.py', target: 'auth', disposition: 'provider', note: 'Mobile authentication/session provider.' },
  { surface: 'apps/api/routers/wallet_auth.py', target: 'auth', disposition: 'provider', note: 'EIP-4361 wallet sign-in provider: single-use server nonce, signer verification and session ownership; never trading permission.' },
  { surface: 'apps/api/routers/captcha.py', target: 'auth', disposition: 'provider', note: 'Bot-abuse/captcha provider owned by auth, never shell logic.' },
  { surface: 'apps/api/routers/assets.py', target: 'market-data', disposition: 'tool', note: 'Asset metadata/read model.' },
  { surface: 'apps/api/routers/market.py', target: 'market-data', disposition: 'service', note: 'Quotes/snapshots/freshness.' },
  { surface: 'apps/api/routers/news.py', target: 'market-data', disposition: 'provider', note: 'News/Market Wire provider surface.' },
  { surface: 'apps/api/routers/hyperliquid_stream.py', target: 'market-data', disposition: 'provider', note: 'Hyperliquid market stream provider; execution remains trading-owned.' },
  { surface: 'apps/api/routers/research.py', target: 'research', disposition: 'service', note: 'Today/overnight/impact/events/opportunities/alerts facts.' },
  { surface: 'apps/api/routers/harness_runs.py', target: 'research', disposition: 'service', note: 'Deep research run lifecycle/artifacts.' },
  { surface: 'apps/api/routers/research_runner.py', target: 'research-runner', disposition: 'provider', note: 'Sandboxed no-network research code execution.' },
  { surface: 'apps/api/routers/reports.py', target: 'research', disposition: 'tool', note: 'Evidence-backed report artifacts.' },
  { surface: 'apps/api/routers/opportunities.py', target: 'research', disposition: 'tool', note: 'Alpha/Gamma opportunity read model.' },
  { surface: 'apps/api/routers/signals.py', target: 'research', disposition: 'tool', note: 'Research signal read model; no direct execution authority.' },
  { surface: 'apps/api/routers/portfolio.py', target: 'portfolio', disposition: 'service', note: 'Accounts, holdings, NAV and connector compatibility.' },
  { surface: 'apps/api/routers/custody.py', target: 'portfolio', disposition: 'provider', note: 'Custody/account connectivity belongs behind portfolio provider seams.' },
  { surface: 'apps/api/routers/options.py', target: 'options', disposition: 'service', note: 'Options chains/surfaces/gamma candidates.' },
  { surface: 'apps/api/routers/backtest.py', target: 'backtest', disposition: 'service', note: 'Backtest execution/result contract.' },
  { surface: 'apps/api/routers/backtest_lab.py', target: 'backtest', disposition: 'client', note: 'Backtest Lab becomes plugin UI + artifacts.' },
  { surface: 'apps/api/routers/memory.py', target: 'memory', disposition: 'service', note: 'Scoped memory/consent/audit.' },
  { surface: 'apps/api/routers/secretary.py', target: 'secretary', disposition: 'service', note: 'Private Secretary, brief, automation and voice.' },
  { surface: 'apps/api/routers/skills.py', target: 'skills', disposition: 'service', note: 'Declarative skill catalog/execution.' },
  { surface: 'apps/api/routers/playbooks.py', target: 'skills', disposition: 'service', note: 'Playbooks become declarative workflow/skill plugins.' },
  { surface: 'apps/api/routers/strategies.py', target: 'trading', disposition: 'service', note: 'Strategy metadata/config; runtime ownership belongs to Nautilus or pg-tsy providers.' },
  { surface: 'apps/api/routers/trading.py', target: 'trading', disposition: 'service', note: 'Execution/risk/order lifecycle.' },
  { surface: 'apps/api/routers/live_trading.py', target: 'trading-mandates', disposition: 'service', note: 'LIVE enablement, approvals, mandates and safety controls.' },
  { surface: 'packages/nautilus + services/nautilus-runtime', target: 'nautilus-runtime', disposition: 'provider', note: 'External execution runtime provider.' },
  { surface: 'vendor/pg-tsy-core-bootstrap', target: 'pg-tsy-runtime', disposition: 'provider', note: 'Pinned Rust quant runtime provider.' },
  { surface: 'apps/api/routers/notifications.py', target: 'notifications', disposition: 'service', note: 'Notification preferences/channels/delivery.' },
  { surface: 'apps/api/routers/imessage_agent.py', target: 'notifications', disposition: 'provider', note: 'iMessage inbound/outbound transport provider.' },
  { surface: 'apps/api/routers/billing.py', target: 'billing', disposition: 'service', note: 'Plans/credits/entitlements/wallet.' },
  { surface: 'apps/api/routers/stripe_webhook.py', target: 'billing', disposition: 'provider', note: 'Stripe event provider/worker.' },
  { surface: 'apps/api/routers/gateway.py', target: 'api-gateway', disposition: 'service', note: 'OpenAI-compatible gateway/model router/keys/usage.' },
  { surface: 'apps/api/routers/mobile.py', target: 'mobile-api', disposition: 'service', note: 'Mobile capabilities/deep links/push contract.' },
  { surface: 'apps/api/routers/mobile_access.py', target: 'mobile-api', disposition: 'provider', note: 'Pocket relay read-only status/QR for users and admin-gated tunnel/PIN changes; relay lifecycle and secrets stay server-side.' },
  { surface: 'apps/api/routers/frontend.py', target: 'admin', disposition: 'compatibility-only', note: 'Legacy frontend manifest/runtime endpoint retires when Harness profile is production entry.' },
  { surface: 'apps/api/routers/internal.py', target: 'admin', disposition: 'compatibility-only', note: 'Internal legacy control endpoints split into owning plugins, then removed.' },
] as const

export function migrationsFor(target: PureGammaCapabilityId): readonly LegacySurfaceMigration[] {
  return LEGACY_SURFACE_MIGRATIONS.filter(item => item.target === target)
}
