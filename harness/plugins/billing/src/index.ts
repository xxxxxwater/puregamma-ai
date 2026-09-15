import { Context, Service } from '@deepseek-ai/cordis'

export type BillingJson = null | boolean | number | string | BillingJson[] | { [key: string]: BillingJson }
export type BillingDocumentKind = 'subscription' | 'credits' | 'ledger' | 'budget' | 'rewards' | 'quote' | 'entitlements' | 'checkout' | 'portal' | 'mutation'

export interface BillingDocument {
  kind: BillingDocumentKind
  observedAt: string
  source: string
  payload: { [key: string]: BillingJson }
}

export interface BillingQuoteRequest {
  taskType?: string
  requestedModel?: string
  inputTokens?: number
  outputTokens?: number
  attachmentBytes?: number
  toolCalls?: string[]
  selectedDataSources?: string[]
  asyncExecution?: boolean
  notificationChannel?: string
}

export interface BillingBudgetRequest {
  dailyLimit: number
  monthlyLimit: number
  perRunLimit: number
  alertThresholdPct?: number
  enabled?: boolean
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgBilling: BillingService
  }
}

/** Billing/credits/entitlements seam. Payment-provider state remains behind providers. */
export abstract class BillingService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgBilling')
  }

  abstract subscription(): Promise<BillingDocument>
  abstract credits(): Promise<BillingDocument>
  abstract ledger(): Promise<BillingDocument>
  abstract budget(): Promise<BillingDocument>
  abstract updateBudget(automationKey: string, request: BillingBudgetRequest): Promise<BillingDocument>
  abstract rewards(): Promise<BillingDocument>
  abstract quote(request?: BillingQuoteRequest): Promise<BillingDocument>
  abstract entitlements(): Promise<BillingDocument>
  abstract createCheckout(planName: string): Promise<BillingDocument>
  abstract createPaymentLinkCheckout(planName: string): Promise<BillingDocument>
  abstract createPortal(): Promise<BillingDocument>
  abstract cancelSubscription(): Promise<BillingDocument>
  abstract reactivateSubscription(): Promise<BillingDocument>
}

export default BillingService
