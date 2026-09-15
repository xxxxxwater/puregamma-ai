import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type {
  PureGammaAccountView,
  PureGammaBillingActionResult,
  PureGammaBillingBudget,
  PureGammaBillingReward,
  PureGammaBillingUsage,
  PureGammaBillingView,
  PureGammaNotificationsView,
  PureGammaQuantRuntimeView,
} from './types.ts'
import type {} from '@puregamma/dsh-auth'
import type {} from '@puregamma/dsh-billing'
import type {} from '@puregamma/dsh-notifications'
import type {} from '@puregamma/dsh-pg-tsy-runtime'

export type {
  PureGammaAccountView,
  PureGammaBillingActionResult,
  PureGammaBillingBudget,
  PureGammaBillingReward,
  PureGammaBillingUsage,
  PureGammaBillingView,
  PureGammaNotificationsView,
  PureGammaQuantRuntimeView,
} from './types.ts'

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : undefined
}

function stringValue(source: Record<string, unknown> | undefined, key: string): string | undefined {
  const value = source?.[key]
  return typeof value === 'string' ? value : undefined
}

function numberValue(source: Record<string, unknown> | undefined, key: string): number | undefined {
  const value = source?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function booleanValue(source: Record<string, unknown> | undefined, key: string): boolean | undefined {
  const value = source?.[key]
  return typeof value === 'boolean' ? value : undefined
}

function stringArray(source: Record<string, unknown> | undefined, key: string): string[] | undefined {
  const value = source?.[key]
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) return undefined
  return [...value] as string[]
}

function objectArray(source: Record<string, unknown> | undefined, key: string): Record<string, unknown>[] {
  const value = source?.[key]
  if (!Array.isArray(value)) return []
  return value.map(record).filter((item): item is Record<string, unknown> => item !== undefined)
}

function booleanRecord(source: Record<string, unknown> | undefined, key: string): Record<string, boolean> | undefined {
  const value = record(source?.[key])
  if (value === undefined) return undefined
  const entries = Object.entries(value).filter(([, item]) => typeof item === 'boolean')
  return Object.fromEntries(entries) as Record<string, boolean>
}

function unavailable<T extends { available: boolean; observedAt: string; source: string; reason?: string }>(source: string, reason: string): T {
  return { available: false, observedAt: new Date().toISOString(), source, reason } as T
}

function normalizePlanName(value: string): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > 80) throw new Error('plan name is invalid')
  return normalized
}

function billingAction(document: { kind: string; observedAt: string; source: string; payload: Record<string, unknown> }, kind: PureGammaBillingActionResult['kind'], planName?: string): PureGammaBillingActionResult {
  const payload = document.payload
  const url = stringValue(payload, 'url')
    ?? stringValue(payload, 'checkout_url')
    ?? stringValue(payload, 'portal_url')
    ?? stringValue(payload, 'session_url')
    ?? stringValue(payload, 'payment_url')
  return {
    available: true,
    observedAt: document.observedAt,
    source: document.source,
    kind,
    ...(planName === undefined ? {} : { planName }),
    status: stringValue(payload, 'status') ?? stringValue(payload, 'subscription_status'),
    ...(url === undefined ? {} : { url }),
  }
}

function billingActionUnavailable(kind: PureGammaBillingActionResult['kind'], source: string, reason: string, planName?: string): PureGammaBillingActionResult {
  return {
    available: false,
    observedAt: new Date().toISOString(),
    source,
    reason,
    kind,
    ...(planName === undefined ? {} : { planName }),
  }
}

function billingBudgetRows(payload: Record<string, unknown> | undefined): PureGammaBillingBudget[] {
  return objectArray(payload, 'budgets').flatMap((item) => {
    const automationKey = stringValue(item, 'automation_key')
    if (automationKey === undefined || automationKey.trim() === '') return []
    return [{
      automationKey,
      dailyLimit: numberValue(item, 'daily_limit'),
      monthlyLimit: numberValue(item, 'monthly_limit'),
      perRunLimit: numberValue(item, 'per_run_limit'),
      dailyUsed: numberValue(item, 'daily_used'),
      monthlyUsed: numberValue(item, 'monthly_used'),
      nextEstimatedCredits: numberValue(item, 'next_estimated_credits'),
      alertThresholdPct: numberValue(item, 'alert_threshold_pct'),
      enabled: booleanValue(item, 'enabled'),
      paused: booleanValue(item, 'paused'),
      pauseReason: stringValue(item, 'pause_reason'),
    }]
  })
}

function billingRewardRows(payload: Record<string, unknown> | undefined): PureGammaBillingReward[] {
  return objectArray(payload, 'rewards').flatMap((item) => {
    const id = stringValue(item, 'id')
    if (id === undefined || id.trim() === '') return []
    return [{
      id,
      rewardType: stringValue(item, 'reward_type'),
      credits: numberValue(item, 'credits'),
      source: stringValue(item, 'source'),
      createdAt: stringValue(item, 'created_at'),
    }]
  })
}

function billingUsageRows(payload: Record<string, unknown> | undefined): PureGammaBillingUsage[] {
  return objectArray(payload, 'usage_history').map((item) => ({
    id: stringValue(item, 'id'),
    action: stringValue(item, 'action'),
    creditsDelta: numberValue(item, 'credits_delta'),
    balanceAfter: numberValue(item, 'balance_after'),
    createdAt: stringValue(item, 'created_at'),
  }))
}

/** Read-only browser projections plus explicit UI action seams. No cache or business state lives here. */
export class PureGammaClientGateway extends TypertRemoteService {
  constructor(ctx: Context) {
    super(ctx, 'puregammaClient')
  }

  @Remote('account')
  async account(): Promise<PureGammaAccountView> {
    const service = this.ctx.get('pgAuth')
    if (service === undefined) return unavailable<PureGammaAccountView>('cordis:pgAuth', 'account capability is not installed')
    try {
      const user = await service.currentUser()
      return {
        available: true, observedAt: new Date().toISOString(), source: 'cordis:pgAuth', id: user.id, email: user.email, name: user.name,
        role: user.role, plan: user.plan, membershipTier: user.membershipTier, creditBalance: user.creditBalance, avatarUrl: user.avatarUrl,
        authProvider: user.authProvider, hasPassword: user.hasPassword, emailVerified: user.emailVerified, emailVerifiedAt: user.emailVerifiedAt,
        lastLoginAt: user.lastLoginAt, loginMethods: [...user.loginMethods], locale: user.locale,
      }
    } catch {
      return unavailable<PureGammaAccountView>('cordis:pgAuth', 'account data is currently unavailable')
    }
  }

  @Remote('billing')
  async billing(): Promise<PureGammaBillingView> {
    const service = this.ctx.get('pgBilling')
    if (service === undefined) return unavailable<PureGammaBillingView>('cordis:pgBilling', 'billing capability is not installed')
    try {
      const [subscription, credits, budget, rewards] = await Promise.all([service.subscription(), service.credits(), service.budget(), service.rewards()])
      const subscriptionPayload = record(subscription.payload)
      const creditsPayload = record(credits.payload)
      const budgetPayload = record(budget.payload)
      const rewardsPayload = record(rewards.payload)
      const entitlement = record(subscriptionPayload?.entitlement ?? subscriptionPayload?.entitlements)
      return {
        available: true, observedAt: new Date().toISOString(), source: subscription.source,
        plan: stringValue(subscriptionPayload, 'plan'), subscribedPlan: stringValue(subscriptionPayload, 'subscribed_plan'),
        effectivePlan: stringValue(subscriptionPayload, 'effective_plan'), subscriptionStatus: stringValue(subscriptionPayload, 'subscription_status'),
        currentPeriodEnd: stringValue(subscriptionPayload, 'current_period_end'), cancelAtPeriodEnd: booleanValue(subscriptionPayload, 'cancel_at_period_end'),
        cancelAt: stringValue(subscriptionPayload, 'cancel_at'), creditBalance: numberValue(subscriptionPayload, 'credit_balance') ?? numberValue(creditsPayload, 'credit_balance'),
        billingMode: stringValue(subscriptionPayload, 'billing_mode'), checkoutMode: stringValue(subscriptionPayload, 'checkout_mode'),
        paymentLinks: booleanRecord(subscriptionPayload, 'payment_links'), primaryPaymentLinkConfigured: booleanValue(subscriptionPayload, 'primary_payment_link_configured'),
        entitlement: entitlement === undefined ? undefined : {
          notificationChannels: stringArray(entitlement, 'notification_channels'), highCostTasks: booleanValue(entitlement, 'high_cost_tasks'), imessage: booleanValue(entitlement, 'imessage'),
        },
        budgets: billingBudgetRows(budgetPayload), rewards: billingRewardRows(rewardsPayload), usageHistory: billingUsageRows(creditsPayload),
      }
    } catch {
      return unavailable<PureGammaBillingView>('cordis:pgBilling', 'billing data is currently unavailable')
    }
  }

  @Remote('billingCheckout')
  async billingCheckout(planName: string): Promise<PureGammaBillingActionResult> {
    const service = this.ctx.get('pgBilling')
    let normalized: string
    try { normalized = normalizePlanName(planName) } catch { return billingActionUnavailable('checkout', 'cordis:pgBilling', 'plan name is invalid', planName) }
    if (service === undefined) return billingActionUnavailable('checkout', 'cordis:pgBilling', 'billing capability is not installed', normalized)
    try { return billingAction(service.createCheckout(normalized), 'checkout', normalized) } catch { return billingActionUnavailable('checkout', 'cordis:pgBilling', 'checkout is currently unavailable', normalized) }
  }

  @Remote('billingPaymentLinkCheckout')
  async billingPaymentLinkCheckout(planName: string): Promise<PureGammaBillingActionResult> {
    const service = this.ctx.get('pgBilling')
    let normalized: string
    try { normalized = normalizePlanName(planName) } catch { return billingActionUnavailable('checkout', 'cordis:pgBilling', 'plan name is invalid', planName) }
    if (service === undefined) return billingActionUnavailable('checkout', 'cordis:pgBilling', 'billing capability is not installed', normalized)
    try { return billingAction(service.createPaymentLinkCheckout(normalized), 'checkout', normalized) } catch { return billingActionUnavailable('checkout', 'cordis:pgBilling', 'payment-link checkout is currently unavailable', normalized) }
  }

  @Remote('billingPortal')
  async billingPortal(): Promise<PureGammaBillingActionResult> {
    const service = this.ctx.get('pgBilling')
    if (service === undefined) return billingActionUnavailable('portal', 'cordis:pgBilling', 'billing capability is not installed')
    try { return billingAction(await service.createPortal(), 'portal') } catch { return billingActionUnavailable('portal', 'cordis:pgBilling', 'billing portal is currently unavailable') }
  }

  @Remote('billingCancel')
  async billingCancel(): Promise<PureGammaBillingActionResult> {
    const service = this.ctx.get('pgBilling')
    if (service === undefined) return billingActionUnavailable('cancel', 'cordis:pgBilling', 'billing capability is not installed')
    try { return billingAction(await service.cancelSubscription(), 'cancel') } catch { return billingActionUnavailable('cancel', 'cordis:pgBilling', 'subscription cancellation is currently unavailable') }
  }

  @Remote('billingReactivate')
  async billingReactivate(): Promise<PureGammaBillingActionResult> {
    const service = this.ctx.get('pgBilling')
    if (service === undefined) return billingActionUnavailable('reactivate', 'cordis:pgBilling', 'billing capability is not installed')
    try { return billingAction(await service.reactivateSubscription(), 'reactivate') } catch { return billingActionUnavailable('reactivate', 'cordis:pgBilling', 'subscription reactivation is currently unavailable') }
  }

  @Remote('notifications')
  async notifications(): Promise<PureGammaNotificationsView> {
    const service = this.ctx.get('pgNotifications')
    if (service === undefined) return unavailable<PureGammaNotificationsView>('cordis:pgNotifications', 'notifications capability is not installed')
    try {
      const [dailyBrief, deliveries] = await Promise.all([service.dailyBrief(), service.deliveries()])
      const dailyPayload = record(dailyBrief.payload)
      const preference = record(dailyPayload?.preference)
      const deliveryRows = objectArray(record(deliveries.payload), 'deliveries')
      const latest = deliveryRows[0]
      return {
        available: true, observedAt: new Date().toISOString(), source: dailyBrief.source, enabled: booleanValue(preference, 'enabled'),
        timezone: stringValue(preference, 'timezone'), localTime: stringValue(preference, 'local_time'), channel: stringValue(preference, 'channel'),
        channels: stringArray(preference, 'channels'), reportTypes: stringArray(preference, 'report_types'), locale: stringValue(preference, 'locale'),
        failureCount: numberValue(preference, 'failure_count'), lastError: stringValue(preference, 'last_error'), nextDeliveryAt: stringValue(preference, 'next_delivery_at'),
        recentDeliveries: deliveryRows.length, lastDeliveryStatus: stringValue(latest, 'status'), lastDeliveryChannel: stringValue(latest, 'channel'),
        lastDeliveryAt: stringValue(latest, 'sent_at') ?? stringValue(latest, 'created_at'),
      }
    } catch {
      return unavailable<PureGammaNotificationsView>('cordis:pgNotifications', 'notification data is currently unavailable')
    }
  }

  @Remote('quantRuntime')
  async quantRuntime(): Promise<PureGammaQuantRuntimeView> {
    const service = this.ctx.get('pgTsyRuntime')
    if (service === undefined) return unavailable<PureGammaQuantRuntimeView>('cordis:pgTsyRuntime', 'pg-tsy runtime capability is not installed')
    try {
      const snapshot = await service.health()
      return {
        available: true, observedAt: snapshot.observedAt, source: snapshot.source, processHealthy: snapshot.processHealthy, ready: snapshot.ready,
        mode: snapshot.mode, leaseHealthy: snapshot.leaseHealthy, feedsTotal: snapshot.feedsTotal, feedsConnected: snapshot.feedsConnected,
        eventsTotal: snapshot.eventsTotal, policyDecisionsTotal: snapshot.policyDecisionsTotal, openOrders: snapshot.openOrders,
        ordersJournaledTotal: snapshot.ordersJournaledTotal, blockingGates: [...snapshot.blockingGates], lastError: snapshot.lastError,
      }
    } catch {
      return unavailable<PureGammaQuantRuntimeView>('cordis:pgTsyRuntime', 'quant runtime health is currently unavailable')
    }
  }
}

export default PureGammaClientGateway
