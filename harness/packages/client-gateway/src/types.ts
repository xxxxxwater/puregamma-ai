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

/**
 * Structural client contract for the generated PureGamma Typert Remote
 * namespace. Keeping this contract beside the Host service prevents the
 * browser assembly from depending on TypeScript module-augmentation identity
 * while the generated Remote artifact remains the runtime transport boundary.
 */
export interface PureGammaClientRemote {
  account(): Promise<PureGammaAccountView>
  billing(): Promise<PureGammaBillingView>
  notifications(): Promise<PureGammaNotificationsView>
  quantRuntime(): Promise<PureGammaQuantRuntimeView>
}
