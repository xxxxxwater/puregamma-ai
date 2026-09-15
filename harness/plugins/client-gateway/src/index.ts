import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type {} from '@puregamma/dsh-auth'
import type {} from '@puregamma/dsh-billing'
import type {} from '@puregamma/dsh-notifications'
import type {} from '@puregamma/dsh-pg-tsy-runtime'

export interface PureGammaAccountView {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  id?: string
  email?: string
  name?: string
  role?: string
  plan?: string
  membershipTier?: string
  creditBalance?: number
  avatarUrl?: string
  authProvider?: string
  hasPassword?: boolean
  emailVerified?: boolean
  emailVerifiedAt?: string
  lastLoginAt?: string
  loginMethods?: string[]
  locale?: string
}

export interface PureGammaBillingView {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  plan?: string
  subscribedPlan?: string
  effectivePlan?: string
  subscriptionStatus?: string
  currentPeriodEnd?: string
  cancelAtPeriodEnd?: boolean
  creditBalance?: number
  billingMode?: string
  checkoutMode?: string
}

export interface PureGammaNotificationsView {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  enabled?: boolean
  timezone?: string
  localTime?: string
  channel?: string
  channels?: string[]
  reportTypes?: string[]
  locale?: string
  failureCount?: number
  lastError?: string
  nextDeliveryAt?: string
  recentDeliveries?: number
  lastDeliveryStatus?: string
  lastDeliveryChannel?: string
  lastDeliveryAt?: string
}

export interface PureGammaQuantRuntimeView {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  processHealthy?: boolean
  ready?: boolean
  mode?: string
  leaseHealthy?: boolean
  feedsTotal?: number
  feedsConnected?: number
  eventsTotal?: number
  policyDecisionsTotal?: number
  openOrders?: number
  ordersJournaledTotal?: number
  blockingGates?: string[]
  lastError?: string
}

function errorDetail(error: unknown): string {
  const value = error instanceof Error ? error.message : String(error)
  return value.slice(0, 300)
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
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

/**
 * Read-only browser projection of PureGamma domain state.
 *
 * The gateway owns no cache and no business state. Every invocation reads the
 * currently composed Cordis service, so removing a provider immediately makes
 * the corresponding view unavailable instead of leaving stale client state.
 * Mutations intentionally stay on their owning services and approval surfaces.
 */
export class PureGammaClientGateway extends TypertRemoteService {
  constructor(ctx: Context) {
    super(ctx, 'puregammaClient')
  }

  @Remote('account')
  async account(): Promise<PureGammaAccountView> {
    const service = this.ctx.get('pgAuth')
    if (service === undefined) {
      return { available: false, observedAt: new Date().toISOString(), source: 'cordis:pgAuth', reason: 'account capability is not installed' }
    }
    try {
      const user = await service.currentUser()
      return {
        available: true,
        observedAt: new Date().toISOString(),
        source: 'cordis:pgAuth',
        id: user.id,
        email: user.email,
        name: user.name,
        role: user.role,
        plan: user.plan,
        membershipTier: user.membershipTier,
        creditBalance: user.creditBalance,
        avatarUrl: user.avatarUrl,
        authProvider: user.authProvider,
        hasPassword: user.hasPassword,
        emailVerified: user.emailVerified,
        emailVerifiedAt: user.emailVerifiedAt,
        lastLoginAt: user.lastLoginAt,
        loginMethods: [...user.loginMethods],
        locale: user.locale,
      }
    } catch (error) {
      return { available: false, observedAt: new Date().toISOString(), source: 'cordis:pgAuth', reason: errorDetail(error) }
    }
  }

  @Remote('billing')
  async billing(): Promise<PureGammaBillingView> {
    const service = this.ctx.get('pgBilling')
    if (service === undefined) {
      return { available: false, observedAt: new Date().toISOString(), source: 'cordis:pgBilling', reason: 'billing capability is not installed' }
    }
    try {
      const [subscription, credits] = await Promise.all([service.subscription(), service.credits()])
      const subscriptionPayload = record(subscription.payload)
      const creditsPayload = record(credits.payload)
      return {
        available: true,
        observedAt: new Date().toISOString(),
        source: subscription.source,
        plan: stringValue(subscriptionPayload, 'plan'),
        subscribedPlan: stringValue(subscriptionPayload, 'subscribed_plan'),
        effectivePlan: stringValue(subscriptionPayload, 'effective_plan'),
        subscriptionStatus: stringValue(subscriptionPayload, 'subscription_status'),
        currentPeriodEnd: stringValue(subscriptionPayload, 'current_period_end'),
        cancelAtPeriodEnd: booleanValue(subscriptionPayload, 'cancel_at_period_end'),
        creditBalance: numberValue(subscriptionPayload, 'credit_balance') ?? numberValue(creditsPayload, 'credit_balance'),
        billingMode: stringValue(subscriptionPayload, 'billing_mode'),
        checkoutMode: stringValue(subscriptionPayload, 'checkout_mode'),
      }
    } catch (error) {
      return { available: false, observedAt: new Date().toISOString(), source: 'cordis:pgBilling', reason: errorDetail(error) }
    }
  }

  @Remote('notifications')
  async notifications(): Promise<PureGammaNotificationsView> {
    const service = this.ctx.get('pgNotifications')
    if (service === undefined) {
      return { available: false, observedAt: new Date().toISOString(), source: 'cordis:pgNotifications', reason: 'notifications capability is not installed' }
    }
    try {
      const [dailyBrief, deliveries] = await Promise.all([service.dailyBrief(), service.deliveries()])
      const dailyPayload = record(dailyBrief.payload)
      const preference = record(dailyPayload?.preference)
      const deliveryRows = objectArray(record(deliveries.payload), 'deliveries')
      const latest = deliveryRows[0]
      return {
        available: true,
        observedAt: new Date().toISOString(),
        source: dailyBrief.source,
        enabled: booleanValue(preference, 'enabled'),
        timezone: stringValue(preference, 'timezone'),
        localTime: stringValue(preference, 'local_time'),
        channel: stringValue(preference, 'channel'),
        channels: stringArray(preference, 'channels'),
        reportTypes: stringArray(preference, 'report_types'),
        locale: stringValue(preference, 'locale'),
        failureCount: numberValue(preference, 'failure_count'),
        lastError: stringValue(preference, 'last_error'),
        nextDeliveryAt: stringValue(preference, 'next_delivery_at'),
        recentDeliveries: deliveryRows.length,
        lastDeliveryStatus: stringValue(latest, 'status'),
        lastDeliveryChannel: stringValue(latest, 'channel'),
        lastDeliveryAt: stringValue(latest, 'sent_at') ?? stringValue(latest, 'created_at'),
      }
    } catch (error) {
      return { available: false, observedAt: new Date().toISOString(), source: 'cordis:pgNotifications', reason: errorDetail(error) }
    }
  }

  @Remote('quantRuntime')
  async quantRuntime(): Promise<PureGammaQuantRuntimeView> {
    const service = this.ctx.get('pgTsyRuntime')
    if (service === undefined) {
      return { available: false, observedAt: new Date().toISOString(), source: 'cordis:pgTsyRuntime', reason: 'pg-tsy runtime capability is not installed' }
    }
    try {
      const snapshot = await service.health()
      return {
        available: true,
        observedAt: snapshot.observedAt,
        source: snapshot.source,
        processHealthy: snapshot.processHealthy,
        ready: snapshot.ready,
        mode: snapshot.mode,
        leaseHealthy: snapshot.leaseHealthy,
        feedsTotal: snapshot.feedsTotal,
        feedsConnected: snapshot.feedsConnected,
        eventsTotal: snapshot.eventsTotal,
        policyDecisionsTotal: snapshot.policyDecisionsTotal,
        openOrders: snapshot.openOrders,
        ordersJournaledTotal: snapshot.ordersJournaledTotal,
        blockingGates: [...snapshot.blockingGates],
        lastError: snapshot.lastError,
      }
    } catch (error) {
      return { available: false, observedAt: new Date().toISOString(), source: 'cordis:pgTsyRuntime', reason: errorDetail(error) }
    }
  }
}

export default PureGammaClientGateway
