import type { PureGammaCapabilityId } from './contracts.js'

export type LegacyWebDisposition = 'harness-native' | 'plugin-ui' | 'public-host-plugin' | 'legacy-redirect'

export interface LegacyWebSurfaceOwner {
  surface: `apps/web/app/${string}/page.tsx`
  owner: PureGammaCapabilityId
  target: string
  disposition: LegacyWebDisposition
}

/**
 * Anti-omission ledger for the legacy Next.js route tree.
 *
 * A row is not permission to preserve the old page. It declares the plugin
 * family and Harness-native surface that must absorb its user-visible behavior
 * before the route can be deleted. Locale-less pages are mostly migration
 * redirects, but are kept here until the old Next.js shell is removed so no
 * public route disappears accidentally.
 */
export const LEGACY_WEB_SURFACES: readonly LegacyWebSurfaceOwner[] = [
  { surface: 'apps/web/app/[locale]/(auth)/forgot-password/page.tsx', owner: 'auth', target: 'settings.account.recovery', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/(auth)/login/page.tsx', owner: 'auth', target: 'conversation.auth.login', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/(auth)/reset-password/page.tsx', owner: 'auth', target: 'settings.account.recovery', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/(auth)/signup/page.tsx', owner: 'auth', target: 'conversation.auth.signup', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/(auth)/verify-email/page.tsx', owner: 'auth', target: 'conversation.auth.verify-email', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/account/page.tsx', owner: 'auth', target: 'settings.account', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/admin/billing-intents/page.tsx', owner: 'admin', target: 'settings.admin.billing-intents', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/admin/gateway/page.tsx', owner: 'admin', target: 'settings.admin.gateway', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/admin/page.tsx', owner: 'admin', target: 'settings.admin', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/admin/stripe-events/page.tsx', owner: 'admin', target: 'settings.admin.stripe-events', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/api/page.tsx', owner: 'api-gateway', target: 'settings.api-gateway.keys', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/auth/google/callback/page.tsx', owner: 'auth', target: 'conversation.auth.oauth-callback', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/backtest/page.tsx', owner: 'backtest', target: 'resource.backtest-artifact', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/billing/cancel/page.tsx', owner: 'billing', target: 'settings.billing.subscription', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/billing/mock-checkout/page.tsx', owner: 'billing', target: 'settings.billing.dev-checkout', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/billing/page.tsx', owner: 'billing', target: 'settings.billing', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/billing/success/page.tsx', owner: 'billing', target: 'settings.billing.subscription', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/chat/[conversationId]/page.tsx', owner: 'agent-chat', target: 'conversation.root', disposition: 'harness-native' },
  { surface: 'apps/web/app/[locale]/chat/page.tsx', owner: 'agent-chat', target: 'conversation.root', disposition: 'harness-native' },
  { surface: 'apps/web/app/[locale]/daily-push/page.tsx', owner: 'notifications', target: 'settings.notifications.daily-brief', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/dashboard/page.tsx', owner: 'agent-chat', target: 'conversation.hero + resources', disposition: 'harness-native' },
  { surface: 'apps/web/app/[locale]/data-sources/page.tsx', owner: 'data-sources', target: 'settings.data-sources', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/docs/page.tsx', owner: 'web-presence', target: 'public.docs', disposition: 'public-host-plugin' },
  { surface: 'apps/web/app/[locale]/gateway/page.tsx', owner: 'api-gateway', target: 'settings.api-gateway', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/integrations/page.tsx', owner: 'data-sources', target: 'settings.data-sources.integrations', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/internal/login/page.tsx', owner: 'auth', target: 'conversation.auth.internal-admin', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/memory/page.tsx', owner: 'memory', target: 'settings.memory', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/mobile-access/page.tsx', owner: 'mobile-api', target: 'settings.mobile-access', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/nautilus/page.tsx', owner: 'nautilus-runtime', target: 'resource.nautilus-runtime', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/news/page.tsx', owner: 'market-data', target: 'tool.market-news', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/onboarding/assets/page.tsx', owner: 'auth', target: 'settings.account.onboarding.assets', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/onboarding/channels/page.tsx', owner: 'auth', target: 'settings.account.onboarding.channels', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/onboarding/style/page.tsx', owner: 'auth', target: 'settings.account.onboarding.style', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/options/page.tsx', owner: 'options', target: 'tool.options-chain + tool.options-surface', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/page.tsx', owner: 'web-presence', target: 'public.landing', disposition: 'public-host-plugin' },
  { surface: 'apps/web/app/[locale]/playbooks/page.tsx', owner: 'skills', target: 'settings.skills.playbooks', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/portfolio/page.tsx', owner: 'portfolio', target: 'resource.portfolio', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/pricing/page.tsx', owner: 'billing', target: 'public.pricing + settings.billing', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/reports/page.tsx', owner: 'research', target: 'resource.research-artifact', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/research/[runId]/page.tsx', owner: 'research-runner', target: 'resource.research-run + ui-workflow-run', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/research/page.tsx', owner: 'research', target: 'tool.research-run + resource.research-artifact', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/secretary/page.tsx', owner: 'secretary', target: 'conversation.secretary-mode', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/signals/page.tsx', owner: 'research', target: 'resource.research-signals', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/strategies/[strategyId]/page.tsx', owner: 'trading', target: 'resource.strategy', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/strategies/page.tsx', owner: 'trading', target: 'settings.trading.strategies', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/trading/live/account/page.tsx', owner: 'trading', target: 'resource.trading-live.account', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/trading/live/connect/page.tsx', owner: 'trading', target: 'settings.trading-live.broker-connection', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/trading/live/orders/page.tsx', owner: 'trading', target: 'resource.trading-live.orders', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/trading/live/page.tsx', owner: 'trading-mandates', target: 'settings.trading-live.safety-and-mandates', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/trading/paper/page.tsx', owner: 'trading', target: 'resource.trading-paper', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/trading/positions/page.tsx', owner: 'trading', target: 'resource.trading-positions', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/trading/risk/page.tsx', owner: 'trading', target: 'resource.trading-status', disposition: 'plugin-ui' },
  { surface: 'apps/web/app/[locale]/trading/runtime/page.tsx', owner: 'pg-tsy-runtime', target: 'resource.quant-runtime', disposition: 'plugin-ui' },

  { surface: 'apps/web/app/account/page.tsx', owner: 'auth', target: 'settings.account', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/admin/billing-intents/page.tsx', owner: 'admin', target: 'settings.admin.billing-intents', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/admin/gateway/page.tsx', owner: 'admin', target: 'settings.admin.gateway', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/admin/page.tsx', owner: 'admin', target: 'settings.admin', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/admin/stripe-events/page.tsx', owner: 'admin', target: 'settings.admin.stripe-events', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/api/page.tsx', owner: 'api-gateway', target: 'settings.api-gateway.keys', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/billing/cancel/page.tsx', owner: 'billing', target: 'settings.billing.subscription', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/billing/mock-checkout/page.tsx', owner: 'billing', target: 'settings.billing.dev-checkout', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/billing/page.tsx', owner: 'billing', target: 'settings.billing', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/billing/success/page.tsx', owner: 'billing', target: 'settings.billing.subscription', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/chat/page.tsx', owner: 'agent-chat', target: 'conversation.root', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/daily-push/page.tsx', owner: 'notifications', target: 'settings.notifications.daily-brief', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/dashboard/page.tsx', owner: 'agent-chat', target: 'conversation.hero + resources', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/data-sources/page.tsx', owner: 'data-sources', target: 'settings.data-sources', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/forgot-password/page.tsx', owner: 'auth', target: 'settings.account.recovery', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/gateway/page.tsx', owner: 'api-gateway', target: 'settings.api-gateway', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/integrations/page.tsx', owner: 'data-sources', target: 'settings.data-sources.integrations', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/internal/login/page.tsx', owner: 'auth', target: 'conversation.auth.internal-admin', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/login/page.tsx', owner: 'auth', target: 'conversation.auth.login', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/mobile-access/page.tsx', owner: 'mobile-api', target: 'settings.mobile-access', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/nautilus/page.tsx', owner: 'nautilus-runtime', target: 'resource.nautilus-runtime', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/news/page.tsx', owner: 'market-data', target: 'tool.market-news', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/onboarding/assets/page.tsx', owner: 'auth', target: 'settings.account.onboarding.assets', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/onboarding/channels/page.tsx', owner: 'auth', target: 'settings.account.onboarding.channels', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/onboarding/style/page.tsx', owner: 'auth', target: 'settings.account.onboarding.style', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/page.tsx', owner: 'web-presence', target: 'public.landing', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/playbooks/page.tsx', owner: 'skills', target: 'settings.skills.playbooks', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/portfolio/page.tsx', owner: 'portfolio', target: 'resource.portfolio', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/privacy/page.tsx', owner: 'web-presence', target: 'public.privacy', disposition: 'public-host-plugin' },
  { surface: 'apps/web/app/reports/page.tsx', owner: 'research', target: 'resource.research-artifact', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/reset-password/page.tsx', owner: 'auth', target: 'settings.account.recovery', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/secretary/page.tsx', owner: 'secretary', target: 'conversation.secretary-mode', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/signals/page.tsx', owner: 'research', target: 'resource.research-signals', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/signup/page.tsx', owner: 'auth', target: 'conversation.auth.signup', disposition: 'legacy-redirect' },
  { surface: 'apps/web/app/terms/page.tsx', owner: 'web-presence', target: 'public.terms', disposition: 'public-host-plugin' },
  { surface: 'apps/web/app/verify-email/page.tsx', owner: 'auth', target: 'conversation.auth.verify-email', disposition: 'legacy-redirect' },
] as const
