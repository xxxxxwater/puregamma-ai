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

export interface PureGammaBillingBudget {
  automationKey: string
  dailyLimit?: number
  monthlyLimit?: number
  perRunLimit?: number
  dailyUsed?: number
  monthlyUsed?: number
  nextEstimatedCredits?: number
  alertThresholdPct?: number
  enabled?: boolean
  paused?: boolean
  pauseReason?: string
}

export interface PureGammaBillingReward {
  id: string
  rewardType?: string
  credits?: number
  source?: string
  createdAt?: string
}

export interface PureGammaBillingUsage {
  id?: string
  action?: string
  creditsDelta?: number
  balanceAfter?: number
  createdAt?: string
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
  cancelAt?: string
  creditBalance?: number
  billingMode?: string
  checkoutMode?: string
  paymentLinks?: Record<string, boolean>
  primaryPaymentLinkConfigured?: boolean
  entitlement?: {
    notificationChannels?: string[]
    highCostTasks?: boolean
    imessage?: boolean
  }
  budgets: PureGammaBillingBudget[]
  rewards: PureGammaBillingReward[]
  usageHistory: PureGammaBillingUsage[]
}

export interface PureGammaBillingActionResult {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  kind: 'checkout' | 'portal' | 'cancel' | 'reactivate'
  planName?: string
  status?: string
  url?: string
}

export interface PureGammaNotificationDelivery {
  id?: string
  channel?: string
  status?: string
  messagePreview?: string
  provider?: string
  error?: string
  createdAt?: string
  sentAt?: string
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
  includePortfolio?: boolean
  includeMarket?: boolean
  includeSignals?: boolean
  includeRisk?: boolean
  includeSentiment?: boolean
  quietHours?: Record<string, string | number | boolean | null>
  maxLength?: number
  failureCount?: number
  lastError?: string
  nextDeliveryAt?: string
  recentDeliveries?: number
  lastDeliveryStatus?: string
  lastDeliveryChannel?: string
  lastDeliveryAt?: string
  deliveryAvailable?: boolean
  imessage?: {
    officialNumber?: string
    provider?: string
    enabledPlans?: string[]
    recipient?: string
    recipientVerifiedAt?: string
  }
  deliveries: PureGammaNotificationDelivery[]
}

export interface PureGammaDailyBriefUpdate {
  enabled?: boolean
  timezone?: string
  localTime?: string
  channel?: string
  channels?: string[]
  reportTypes?: string[]
  locale?: string
  includePortfolio?: boolean
  includeMarket?: boolean
  includeSignals?: boolean
  includeRisk?: boolean
  includeSentiment?: boolean
  quietHours?: Record<string, string | number | boolean | null>
  maxLength?: number
}

export interface PureGammaNotificationActionResult {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  kind: 'preferences' | 'imessage-verify-request' | 'imessage-verify-confirm' | 'imessage-test' | 'email-test'
  challengeId?: string
  recipient?: string
  status?: string
  deliveryId?: string
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
