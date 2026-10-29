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

/** Explicit wire fields only. Missing values remain optional, never invented. */
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

/**
 * Deep-research run as the browser sees it. Every field is copied from the
 * server payload or left undefined: a missing count is not a zero.
 */
export interface PureGammaResearchRunSummary {
  id: string
  name?: string
  status?: string
  verification?: string
  createdAt?: string
  updatedAt?: string
  evidenceCount?: number
  citationCount?: number
  creditsUsed?: number
  degraded?: boolean
  errorMessage?: string
  summary?: string
  disclaimer?: string
  dataSources?: string[]
}

export interface PureGammaResearchRunView {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  /** True once the run reached a state it never leaves (completed, degraded, failed, canceled, timed_out). */
  terminal?: boolean
  run?: PureGammaResearchRunSummary
}

export interface PureGammaResearchRunsView {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  total?: number
  runs: PureGammaResearchRunSummary[]
}

export interface PureGammaResearchArtifact {
  id: string
  type?: string
  title?: string
  status?: string
  createdAt?: string
  /** Rendered report text, capped; `markdownTruncated` says when it was cut. */
  markdown?: string
  markdownTruncated?: boolean
}

export interface PureGammaResearchEvidence {
  id?: string
  title?: string
  source?: string
  /** Only http(s) citation links are forwarded. */
  url?: string
  publishedAt?: string
  snippet?: string
}

export interface PureGammaResearchArtifactsView {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  runId?: string
  artifacts: PureGammaResearchArtifact[]
  /** `evidenceAvailable: false` when the evidence read failed while artifacts succeeded. */
  evidenceAvailable?: boolean
  evidence: PureGammaResearchEvidence[]
}

export interface PureGammaBacktestMetric {
  name: string
  value: number
}

/** Artifact metadata only: no server path, no download URL, no credential. */
export interface PureGammaBacktestArtifactFile {
  id: string
  artifactType?: string
  format?: string
  sizeBytes?: number
  checksum?: string
  createdAt?: string
}

export interface PureGammaBacktestRunSummary {
  id: string
  status?: string
  engine?: string
  strategyName?: string
  asset?: string
  createdAt?: string
  completedAt?: string
}

export interface PureGammaBacktestArtifactView {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  run?: PureGammaBacktestRunSummary & {
    windowStart?: string
    windowEnd?: string
    errorMessage?: string
    isLegacy?: boolean
  }
  metrics: PureGammaBacktestMetric[]
  artifacts: PureGammaBacktestArtifactFile[]
}

export interface PureGammaBacktestRunsView {
  available: boolean
  observedAt: string
  source: string
  reason?: string
  total?: number
  runs: PureGammaBacktestRunSummary[]
}
