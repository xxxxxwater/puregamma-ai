import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type {
  PureGammaAccountView, PureGammaBillingActionResult, PureGammaBillingBudget, PureGammaBillingReward, PureGammaBillingUsage, PureGammaBillingView,
  PureGammaDailyBriefUpdate, PureGammaNotificationActionResult, PureGammaNotificationDelivery, PureGammaNotificationsView,
  PureGammaPmAccountView, PureGammaPmNavHistoryView, PureGammaQuantRuntimeView, PmBag, PmNavPoint,
} from './types.ts'
import type {} from '@puregamma/dsh-auth'
import type {} from '@puregamma/dsh-billing'
import type {} from '@puregamma/dsh-notifications'
import type {} from '@puregamma/dsh-pg-tsy-runtime'
import type {} from '@puregamma/dsh-pm-nav'

export type {
  PureGammaAccountView, PureGammaBillingActionResult, PureGammaBillingBudget, PureGammaBillingReward, PureGammaBillingUsage, PureGammaBillingView,
  PureGammaDailyBriefUpdate, PureGammaNotificationActionResult, PureGammaNotificationDelivery, PureGammaNotificationsView,
  PureGammaPmAccountView, PureGammaPmNavHistoryView, PureGammaQuantRuntimeView, PmBag, PmNavPoint,
} from './types.ts'

function record(value: unknown): Record<string, unknown> | undefined { return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : undefined }
// Read a structurally typed projection without requiring an unsafe index signature in the wire DTO.
function stringValue(source: object | undefined, key: string): string | undefined { const value = record(source)?.[key]; return typeof value === 'string' ? value : undefined }
function numberValue(source: Record<string, unknown> | undefined, key: string): number | undefined { const value = source?.[key]; return typeof value === 'number' && Number.isFinite(value) ? value : undefined }
function booleanValue(source: Record<string, unknown> | undefined, key: string): boolean | undefined { const value = source?.[key]; return typeof value === 'boolean' ? value : undefined }
function stringArray(source: Record<string, unknown> | undefined, key: string): string[] | undefined { const value = source?.[key]; if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) return undefined; return [...value] as string[] }
function objectArray(source: Record<string, unknown> | undefined, key: string): Record<string, unknown>[] { const value = source?.[key]; if (!Array.isArray(value)) return []; return value.map(record).filter((item): item is Record<string, unknown> => item !== undefined) }
function booleanRecord(source: Record<string, unknown> | undefined, key: string): Record<string, boolean> | undefined { const value = record(source?.[key]); if (value === undefined) return undefined; return Object.fromEntries(Object.entries(value).filter(([, item]) => typeof item === 'boolean')) as Record<string, boolean> }
function pmScalar(value: unknown): string | number | boolean | null { return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? value : null }
// A provider row is a flat scalar bag. Keys whose value is not a scalar are
// omitted rather than flattened into a misleading null.
function pmBag(value: unknown): PmBag | undefined { const source = record(value); if (source === undefined) return undefined; const bag: PmBag = {}; for (const [key, item] of Object.entries(source)) { const scalar = pmScalar(item); if (scalar !== null || item === null) bag[key] = scalar } return bag }
function pmBags(value: unknown): PmBag[] { if (!Array.isArray(value)) return []; return value.flatMap(item => { const bag = pmBag(item); return bag === undefined ? [] : [bag] }) }
function pmStringList(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [] }
function pmNullableBool(value: unknown): boolean | null { return typeof value === 'boolean' ? value : null }
function pmNullableNumber(value: unknown): number | null { return typeof value === 'number' && Number.isFinite(value) ? value : null }
/** Decimal strings and finite numbers only; a boolean is never a money figure. */
function pmDecimal(value: unknown): string | number | null { return typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value)) ? value : null }
function pmNullableText(value: unknown): string | null { return typeof value === 'string' && value.trim().length > 0 ? value : null }
function unavailable<T extends { available: boolean; observedAt: string; source: string; reason?: string }>(source: string, reason: string): T { return { available: false, observedAt: new Date().toISOString(), source, reason } as T }
function safeText(value: string, max: number): string { const normalized = value.trim(); if (!normalized || normalized.length > max) throw new Error('invalid text'); return normalized }
function normalizePlanName(value: string): string { return safeText(value, 80) }
function billingAction(document: { observedAt: string; source: string; payload: Record<string, unknown> }, kind: PureGammaBillingActionResult['kind'], planName?: string): PureGammaBillingActionResult { const payload = document.payload; const url = stringValue(payload, 'url') ?? stringValue(payload, 'checkout_url') ?? stringValue(payload, 'portal_url') ?? stringValue(payload, 'session_url') ?? stringValue(payload, 'payment_url'); return { available: true, observedAt: document.observedAt, source: document.source, kind, ...(planName === undefined ? {} : { planName }), status: stringValue(payload, 'status') ?? stringValue(payload, 'subscription_status'), ...(url === undefined ? {} : { url }) } }
function billingActionUnavailable(kind: PureGammaBillingActionResult['kind'], source: string, reason: string, planName?: string): PureGammaBillingActionResult { return { available: false, observedAt: new Date().toISOString(), source, reason, kind, ...(planName === undefined ? {} : { planName }) } }
function notificationAction(document: { observedAt: string; source: string; payload: Record<string, unknown> }, kind: PureGammaNotificationActionResult['kind']): PureGammaNotificationActionResult { const payload = document.payload, delivery = record(payload.delivery), verification = record(payload.verification); return { available: true, observedAt: document.observedAt, source: document.source, kind, challengeId: stringValue(payload, 'challenge_id') ?? stringValue(verification, 'challenge_id'), recipient: stringValue(payload, 'recipient'), status: stringValue(payload, 'status') ?? stringValue(delivery, 'status'), deliveryId: stringValue(payload, 'delivery_id') ?? stringValue(delivery, 'id') } }
function notificationActionUnavailable(kind: PureGammaNotificationActionResult['kind'], reason: string): PureGammaNotificationActionResult { return { available: false, observedAt: new Date().toISOString(), source: 'cordis:pgNotifications', reason, kind } }
function notificationDeliveries(payload: Record<string, unknown> | undefined): PureGammaNotificationDelivery[] { return objectArray(payload, 'deliveries').map((item) => ({ id: stringValue(item, 'id'), channel: stringValue(item, 'channel'), status: stringValue(item, 'status'), messagePreview: stringValue(item, 'message_preview') ?? stringValue(item, 'message'), provider: stringValue(item, 'provider'), error: stringValue(item, 'error'), createdAt: stringValue(item, 'created_at'), sentAt: stringValue(item, 'sent_at') })) }
function billingBudgetRows(payload: Record<string, unknown> | undefined): PureGammaBillingBudget[] { return objectArray(payload, 'budgets').flatMap((item) => { const automationKey = stringValue(item, 'automation_key'); if (automationKey === undefined || automationKey.trim() === '') return []; return [{ automationKey, dailyLimit: numberValue(item, 'daily_limit'), monthlyLimit: numberValue(item, 'monthly_limit'), perRunLimit: numberValue(item, 'per_run_limit'), dailyUsed: numberValue(item, 'daily_used'), monthlyUsed: numberValue(item, 'monthly_used'), nextEstimatedCredits: numberValue(item, 'next_estimated_credits'), alertThresholdPct: numberValue(item, 'alert_threshold_pct'), enabled: booleanValue(item, 'enabled'), paused: booleanValue(item, 'paused'), pauseReason: stringValue(item, 'pause_reason') }] }) }
function billingRewardRows(payload: Record<string, unknown> | undefined): PureGammaBillingReward[] { return objectArray(payload, 'rewards').flatMap((item) => { const id = stringValue(item, 'id'); if (id === undefined || id.trim() === '') return []; return [{ id, rewardType: stringValue(item, 'reward_type'), credits: numberValue(item, 'credits'), source: stringValue(item, 'source'), createdAt: stringValue(item, 'created_at') }] }) }
function billingUsageRows(payload: Record<string, unknown> | undefined): PureGammaBillingUsage[] { return objectArray(payload, 'usage_history').map((item) => ({ id: stringValue(item, 'id'), action: stringValue(item, 'action'), creditsDelta: numberValue(item, 'credits_delta'), balanceAfter: numberValue(item, 'balance_after'), createdAt: stringValue(item, 'created_at') })) }

export class PureGammaClientGateway extends TypertRemoteService {
  constructor(ctx: Context) { super(ctx, 'puregammaClient') }
  @Remote('account')
  async account(): Promise<PureGammaAccountView> { const service = this.ctx.get('pgAuth'); if (service === undefined) return unavailable<PureGammaAccountView>('cordis:pgAuth', 'account capability is not installed'); try { const user = await service.currentUser(); return { available: true, observedAt: new Date().toISOString(), source: 'cordis:pgAuth', id: user.id, email: user.email, name: user.name, role: user.role, plan: user.plan, membershipTier: user.membershipTier, creditBalance: user.creditBalance, avatarUrl: user.avatarUrl, authProvider: user.authProvider, hasPassword: user.hasPassword, emailVerified: user.emailVerified, emailVerifiedAt: user.emailVerifiedAt, lastLoginAt: user.lastLoginAt, loginMethods: [...user.loginMethods], locale: user.locale } } catch { return unavailable<PureGammaAccountView>('cordis:pgAuth', 'account data is currently unavailable') } }
  @Remote('billing')
  async billing(): Promise<PureGammaBillingView> { const service = this.ctx.get('pgBilling'); if (service === undefined) return unavailable<PureGammaBillingView>('cordis:pgBilling', 'billing capability is not installed'); try { const [subscription, credits, budget, rewards] = await Promise.all([service.subscription(), service.credits(), service.budget(), service.rewards()]); const subscriptionPayload = record(subscription.payload), creditsPayload = record(credits.payload), budgetPayload = record(budget.payload), rewardsPayload = record(rewards.payload), entitlement = record(subscriptionPayload?.entitlement ?? subscriptionPayload?.entitlements); return { available: true, observedAt: new Date().toISOString(), source: subscription.source, plan: stringValue(subscriptionPayload, 'plan'), subscribedPlan: stringValue(subscriptionPayload, 'subscribed_plan'), effectivePlan: stringValue(subscriptionPayload, 'effective_plan'), subscriptionStatus: stringValue(subscriptionPayload, 'subscription_status'), currentPeriodEnd: stringValue(subscriptionPayload, 'current_period_end'), cancelAtPeriodEnd: booleanValue(subscriptionPayload, 'cancel_at_period_end'), cancelAt: stringValue(subscriptionPayload, 'cancel_at'), creditBalance: numberValue(subscriptionPayload, 'credit_balance') ?? numberValue(creditsPayload, 'credit_balance'), billingMode: stringValue(subscriptionPayload, 'billing_mode'), checkoutMode: stringValue(subscriptionPayload, 'checkout_mode'), paymentLinks: booleanRecord(subscriptionPayload, 'payment_links'), primaryPaymentLinkConfigured: booleanValue(subscriptionPayload, 'primary_payment_link_configured'), entitlement: entitlement === undefined ? undefined : { notificationChannels: stringArray(entitlement, 'notification_channels'), highCostTasks: booleanValue(entitlement, 'high_cost_tasks'), imessage: booleanValue(entitlement, 'imessage') }, budgets: billingBudgetRows(budgetPayload), rewards: billingRewardRows(rewardsPayload), usageHistory: billingUsageRows(creditsPayload) } } catch { return unavailable<PureGammaBillingView>('cordis:pgBilling', 'billing data is currently unavailable') } }
  @Remote('billingCheckout')
  async billingCheckout(planName: string): Promise<PureGammaBillingActionResult> { const service = this.ctx.get('pgBilling'); let normalized: string; try { normalized = normalizePlanName(planName) } catch { return billingActionUnavailable('checkout', 'cordis:pgBilling', 'plan name is invalid', planName) }; if (service === undefined) return billingActionUnavailable('checkout', 'cordis:pgBilling', 'billing capability is not installed', normalized); try { return billingAction(await service.createCheckout(normalized), 'checkout', normalized) } catch { return billingActionUnavailable('checkout', 'cordis:pgBilling', 'checkout is currently unavailable', normalized) } }
  @Remote('billingPaymentLinkCheckout')
  async billingPaymentLinkCheckout(planName: string): Promise<PureGammaBillingActionResult> { const service = this.ctx.get('pgBilling'); let normalized: string; try { normalized = normalizePlanName(planName) } catch { return billingActionUnavailable('checkout', 'cordis:pgBilling', 'plan name is invalid', planName) }; if (service === undefined) return billingActionUnavailable('checkout', 'cordis:pgBilling', 'billing capability is not installed', normalized); try { return billingAction(await service.createPaymentLinkCheckout(normalized), 'checkout', normalized) } catch { return billingActionUnavailable('checkout', 'cordis:pgBilling', 'payment-link checkout is currently unavailable', normalized) } }
  @Remote('billingPortal')
  async billingPortal(): Promise<PureGammaBillingActionResult> { const service = this.ctx.get('pgBilling'); if (service === undefined) return billingActionUnavailable('portal', 'cordis:pgBilling', 'billing capability is not installed'); try { return billingAction(await service.createPortal(), 'portal') } catch { return billingActionUnavailable('portal', 'cordis:pgBilling', 'billing portal is currently unavailable') } }
  @Remote('billingCancel')
  async billingCancel(): Promise<PureGammaBillingActionResult> { const service = this.ctx.get('pgBilling'); if (service === undefined) return billingActionUnavailable('cancel', 'cordis:pgBilling', 'billing capability is not installed'); try { return billingAction(await service.cancelSubscription(), 'cancel') } catch { return billingActionUnavailable('cancel', 'cordis:pgBilling', 'subscription cancellation is currently unavailable') } }
  @Remote('billingReactivate')
  async billingReactivate(): Promise<PureGammaBillingActionResult> { const service = this.ctx.get('pgBilling'); if (service === undefined) return billingActionUnavailable('reactivate', 'cordis:pgBilling', 'billing capability is not installed'); try { return billingAction(await service.reactivateSubscription(), 'reactivate') } catch { return billingActionUnavailable('reactivate', 'cordis:pgBilling', 'subscription reactivation is currently unavailable') } }
  @Remote('notifications')
  async notifications(): Promise<PureGammaNotificationsView> { const service = this.ctx.get('pgNotifications'); if (service === undefined) return unavailable<PureGammaNotificationsView>('cordis:pgNotifications', 'notifications capability is not installed'); try { const [dailyBrief, deliveries, imessageConfig, devices] = await Promise.all([service.dailyBrief(), service.deliveries(), service.imessageConfig(), service.devices()]); const dailyPayload = record(dailyBrief.payload), preference = record(dailyPayload?.preference), deliveryRows = notificationDeliveries(record(deliveries.payload)), latest = deliveryRows[0], imessage = record(imessageConfig.payload), devicePayload = record(devices.payload); return { available: true, observedAt: new Date().toISOString(), source: dailyBrief.source, enabled: booleanValue(preference, 'enabled'), timezone: stringValue(preference, 'timezone'), localTime: stringValue(preference, 'local_time'), channel: stringValue(preference, 'channel'), channels: stringArray(preference, 'channels'), reportTypes: stringArray(preference, 'report_types'), locale: stringValue(preference, 'locale'), includePortfolio: booleanValue(preference, 'include_portfolio'), includeMarket: booleanValue(preference, 'include_market'), includeSignals: booleanValue(preference, 'include_signals'), includeRisk: booleanValue(preference, 'include_risk'), includeSentiment: booleanValue(preference, 'include_sentiment'), maxLength: numberValue(preference, 'max_length'), quietHours: record(preference?.quiet_hours) as PureGammaNotificationsView['quietHours'], failureCount: numberValue(preference, 'failure_count'), lastError: stringValue(preference, 'last_error'), nextDeliveryAt: stringValue(preference, 'next_delivery_at'), recentDeliveries: deliveryRows.length, lastDeliveryStatus: latest?.status, lastDeliveryChannel: latest?.channel, lastDeliveryAt: latest?.sentAt ?? latest?.createdAt, deliveryAvailable: booleanValue(devicePayload, 'delivery_available'), imessage: imessage === undefined ? undefined : { officialNumber: stringValue(imessage, 'official_number'), provider: stringValue(imessage, 'provider'), enabledPlans: stringArray(imessage, 'enabled_plans'), recipient: stringValue(imessage, 'recipient'), recipientVerifiedAt: stringValue(imessage, 'recipient_verified_at') }, deliveries: deliveryRows } } catch { return unavailable<PureGammaNotificationsView>('cordis:pgNotifications', 'notification data is currently unavailable') } }
  @Remote('notificationsUpdateDailyBrief')
  async notificationsUpdateDailyBrief(request: PureGammaDailyBriefUpdate): Promise<PureGammaNotificationActionResult> { const service = this.ctx.get('pgNotifications'); if (service === undefined) return notificationActionUnavailable('preferences', 'notifications capability is not installed'); try { return notificationAction(await service.updateDailyBrief(request), 'preferences') } catch { return notificationActionUnavailable('preferences', 'notification preferences could not be updated') } }
  @Remote('notificationsRequestImessageVerification')
  async notificationsRequestImessageVerification(recipient: string): Promise<PureGammaNotificationActionResult> { const service = this.ctx.get('pgNotifications'); let normalized: string; try { normalized = safeText(recipient, 160) } catch { return notificationActionUnavailable('imessage-verify-request', 'iMessage recipient is invalid') }; if (service === undefined) return notificationActionUnavailable('imessage-verify-request', 'notifications capability is not installed'); try { return notificationAction(await service.requestImessageVerification(normalized), 'imessage-verify-request') } catch { return notificationActionUnavailable('imessage-verify-request', 'iMessage verification request is currently unavailable') } }
  @Remote('notificationsConfirmImessageVerification')
  async notificationsConfirmImessageVerification(challengeId: string, code: string): Promise<PureGammaNotificationActionResult> { const service = this.ctx.get('pgNotifications'); let challenge: string, normalizedCode: string; try { challenge = safeText(challengeId, 160); normalizedCode = safeText(code, 32) } catch { return notificationActionUnavailable('imessage-verify-confirm', 'verification input is invalid') }; if (service === undefined) return notificationActionUnavailable('imessage-verify-confirm', 'notifications capability is not installed'); try { return notificationAction(await service.confirmImessageVerification(challenge, normalizedCode), 'imessage-verify-confirm') } catch { return notificationActionUnavailable('imessage-verify-confirm', 'iMessage verification could not be confirmed') } }
  @Remote('notificationsTestImessage')
  async notificationsTestImessage(): Promise<PureGammaNotificationActionResult> { const service = this.ctx.get('pgNotifications'); if (service === undefined) return notificationActionUnavailable('imessage-test', 'notifications capability is not installed'); try { return notificationAction(await service.testImessage(), 'imessage-test') } catch { return notificationActionUnavailable('imessage-test', 'iMessage test delivery is currently unavailable') } }
  @Remote('notificationsTestEmail')
  async notificationsTestEmail(): Promise<PureGammaNotificationActionResult> { const service = this.ctx.get('pgNotifications'); if (service === undefined) return notificationActionUnavailable('email-test', 'notifications capability is not installed'); try { const idempotencyKey = `ui-test:${Date.now().toString(36)}:${Math.random().toString(36).slice(2, 12)}`; return notificationAction(await service.send({ channel: 'email', message: 'PureGamma AI test notification.', idempotencyKey }), 'email-test') } catch { return notificationActionUnavailable('email-test', 'email test delivery is currently unavailable') } }
  @Remote('quantRuntime')
  async quantRuntime(): Promise<PureGammaQuantRuntimeView> { const service = this.ctx.get('pgTsyRuntime'); if (service === undefined) return unavailable<PureGammaQuantRuntimeView>('cordis:pgTsyRuntime', 'pg-tsy runtime capability is not installed'); try { const snapshot = await service.health(); return { available: true, observedAt: snapshot.observedAt, source: snapshot.source, processHealthy: snapshot.processHealthy, ready: snapshot.ready, mode: snapshot.mode, leaseHealthy: snapshot.leaseHealthy, feedsTotal: snapshot.feedsTotal, feedsConnected: snapshot.feedsConnected, eventsTotal: snapshot.eventsTotal, policyDecisionsTotal: snapshot.policyDecisionsTotal, openOrders: snapshot.openOrders, ordersJournaledTotal: snapshot.ordersJournaledTotal, blockingGates: [...snapshot.blockingGates], lastError: snapshot.lastError } } catch { return unavailable<PureGammaQuantRuntimeView>('cordis:pgTsyRuntime', 'quant runtime health is currently unavailable') } }

  /**
   * Private Binance PM account. The allowlist is enforced inside the host
   * service from the authenticated session; this projection never accepts an
   * identity from the browser, and a refusal arrives as `available: false` with
   * no account data attached.
   */
  @Remote('pmAccount')
  async pmAccount(): Promise<PureGammaPmAccountView> {
    const service = this.ctx.get('pgPmNav')
    if (service === undefined) return unavailable<PureGammaPmAccountView>('cordis:pgPmNav', 'private PM account capability is not installed')
    try {
      const view = await service.account()
      const risk = view.risk
      const coverage = view.coverage
      const quality = view.quality
      const ordersMeta = view.ordersMeta
      return {
        available: view.available,
        observedAt: new Date().toISOString(),
        source: 'cordis:pgPmNav',
        ...(view.reason === undefined ? {} : { reason: view.reason }),
        label: view.label,
        mergedIntoPortfolioNav: view.mergedIntoPortfolioNav,
        venue: view.source.venue,
        sourceNote: view.source.note,
        ...(view.stale === undefined ? {} : { stale: view.stale }),
        ...(view.partial === undefined ? {} : { partial: view.partial }),
        ...(view.ageSeconds === undefined ? {} : { ageSeconds: view.ageSeconds }),
        ...(view.staleAfterSeconds === undefined ? {} : { staleAfterSeconds: view.staleAfterSeconds }),
        ...(view.dataAsOf === undefined ? {} : { dataAsOf: view.dataAsOf }),
        ...(view.generatedAt === undefined ? {} : { generatedAt: view.generatedAt }),
        ...(view.disclaimer === undefined ? {} : { disclaimer: view.disclaimer }),
        ...(view.available ? {
          collector: pmBag(view.collector),
          account: pmBag(view.account),
          btc: pmBag(view.btc),
          exposure: pmBag(view.exposure),
          balances: pmBags(view.balances),
          positions: pmBags(view.positions),
          orders: pmBags(view.orders),
          ordersMeta: {
            capturedAt: pmNullableText(ordersMeta?.capturedAt),
            ageSeconds: pmNullableNumber(ordersMeta?.ageSeconds),
            fullyCovered: pmNullableBool(ordersMeta?.fullyCovered),
            refreshIntervalSeconds: pmNullableNumber(ordersMeta?.refreshIntervalSeconds),
          },
          risk: {
            firingCount: pmNullableNumber(risk?.firingCount) ?? 0,
            firing: pmBags(risk?.firing),
            drawdownPeakBtcEquivalent: pmDecimal(risk?.drawdownPeakBtcEquivalent),
            drawdownDayBtcEquivalent: pmDecimal(risk?.drawdownDayBtcEquivalent),
          },
          coverage: {
            essentialOk: pmNullableBool(coverage?.essentialOk),
            ordersCovered: pmNullableBool(coverage?.ordersCovered),
            failures: pmStringList(coverage?.failures),
            essentialFailures: pmStringList(coverage?.essentialFailures),
          },
          quality: {
            restOk: pmNullableBool(quality?.restOk),
            wsConnected: pmNullableBool(quality?.wsConnected),
            mismatch: pmNullableBool(quality?.mismatch),
            lastError: pmNullableText(quality?.lastError),
          },
        } : {}),
      }
    } catch { return unavailable<PureGammaPmAccountView>('cordis:pgPmNav', 'private PM account data is currently unavailable') }
  }

  /** Observations written by the read-only collector only; gaps are kept. */
  @Remote('pmNavHistory')
  async pmNavHistory(): Promise<PureGammaPmNavHistoryView> {
    const service = this.ctx.get('pgPmNav')
    if (service === undefined) return { ...unavailable<PureGammaPmNavHistoryView>('cordis:pgPmNav', 'private PM account capability is not installed'), points: [] }
    try {
      const view = await service.navHistory()
      return {
        available: view.available,
        observedAt: new Date().toISOString(),
        source: 'cordis:pgPmNav',
        ...(view.reason === undefined ? {} : { reason: view.reason }),
        ...(view.firstPointAt === undefined ? {} : { firstPointAt: view.firstPointAt }),
        ...(view.pointCount === undefined ? {} : { pointCount: view.pointCount }),
        ...(view.sufficient === undefined ? {} : { sufficient: view.sufficient }),
        ...(view.windowDays === undefined ? {} : { windowDays: view.windowDays }),
        ...(view.intervalHintSeconds === undefined ? {} : { intervalHintSeconds: view.intervalHintSeconds }),
        ...(view.sampling === undefined ? {} : { sampling: typeof view.sampling === 'string' ? view.sampling : undefined }),
        points: view.points.flatMap(point => {
          const row = record(point)
          const t = pmNullableNumber(row?.t)
          if (t === null) return []
          return [{ t, adjustedEquityUsd: pmDecimal(row?.adjusted_equity_usd), btcPriceUsd: pmDecimal(row?.btc_price_usd) }]
        }),
      }
    } catch { return { ...unavailable<PureGammaPmNavHistoryView>('cordis:pgPmNav', 'private PM NAV history is currently unavailable'), points: [] } }
  }
}

export default PureGammaClientGateway
