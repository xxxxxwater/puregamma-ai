import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import BillingService, {
  type BillingBudgetRequest,
  type BillingDocument,
  type BillingDocumentKind,
  type BillingJson,
  type BillingQuoteRequest,
} from '@puregamma/dsh-billing'

export interface Config { baseUrl?: string; authTokenEnv?: string; requestTimeoutMs?: number }
export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(60000).default(15000),
})

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function toJson(value: unknown, path = '$'): BillingJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`billing payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const out: Record<string, BillingJson> = {}
    for (const [key, item] of Object.entries(value)) out[key] = toJson(item, `${path}.${key}`)
    return out
  }
  throw new Error(`billing payload contains non-JSON value at ${path}`)
}
function toRecord(value: unknown): Record<string, BillingJson> {
  if (!isRecord(value)) throw new Error('billing compatibility API returned a non-object payload')
  return toJson(value) as Record<string, BillingJson>
}
function key(value: string, label: string): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > 120 || !normalized.replace(/[_-]/g, '').match(/^[A-Za-z0-9]+$/)) throw new Error(`${label} is invalid`)
  return normalized
}
function plan(value: string): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > 80) throw new Error('plan name is invalid')
  return normalized
}

export class LegacyApiBillingProvider extends BillingService {
  static Config = Config
  private readonly baseUrl: string
  private readonly tokenEnv: string
  private readonly timeoutMs: number
  private readonly controllers = new Set<AbortController>()

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.tokenEnv = config.authTokenEnv ?? 'PUREGAMMA_LEGACY_API_TOKEN'
    this.timeoutMs = config.requestTimeoutMs ?? 15000
    ctx.effect(() => () => {
      for (const controller of this.controllers) controller.abort()
      this.controllers.clear()
    }, 'pgBilling.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness billing compatibility provider requires bearer token in ${this.tokenEnv}`)
    return token
  }

  private async request(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown): Promise<Record<string, BillingJson>> {
    const controller = new AbortController()
    this.controllers.add(controller)
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(new URL(`${this.baseUrl}${path}`), {
        method,
        signal: controller.signal,
        headers: { Accept: 'application/json', Authorization: `Bearer ${this.token()}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      })
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 500)
        throw new Error(`billing compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      return toRecord(await response.json())
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private document(kind: BillingDocumentKind, payload: Record<string, BillingJson>): BillingDocument {
    return { kind, observedAt: new Date().toISOString(), source: 'compatibility:billing-api', payload }
  }

  async subscription(): Promise<BillingDocument> { return this.document('subscription', await this.request('GET', '/billing/subscription')) }
  async credits(): Promise<BillingDocument> { return this.document('credits', await this.request('GET', '/billing/credits')) }
  async ledger(): Promise<BillingDocument> { return this.document('ledger', await this.request('GET', '/billing/ledger')) }
  async budget(): Promise<BillingDocument> { return this.document('budget', await this.request('GET', '/billing/budget')) }
  async rewards(): Promise<BillingDocument> { return this.document('rewards', await this.request('GET', '/billing/rewards')) }
  async entitlements(): Promise<BillingDocument> { return this.document('entitlements', await this.request('GET', '/billing/capabilities')) }

  async updateBudget(automationKey: string, request: BillingBudgetRequest): Promise<BillingDocument> {
    if (!Number.isInteger(request.dailyLimit) || !Number.isInteger(request.monthlyLimit) || !Number.isInteger(request.perRunLimit)) throw new Error('billing budget limits must be integers')
    if (request.perRunLimit > request.dailyLimit || request.dailyLimit > request.monthlyLimit) throw new Error('billing budget limits are inconsistent')
    return this.document('budget', await this.request('PUT', `/billing/budget/${encodeURIComponent(key(automationKey, 'automation key'))}`, {
      daily_limit: request.dailyLimit,
      monthly_limit: request.monthlyLimit,
      per_run_limit: request.perRunLimit,
      alert_threshold_pct: request.alertThresholdPct ?? 80,
      enabled: request.enabled ?? true,
    }))
  }

  async quote(request: BillingQuoteRequest = {}): Promise<BillingDocument> {
    return this.document('quote', await this.request('POST', '/billing/quote', {
      task_type: request.taskType ?? 'default_chat',
      requested_model: request.requestedModel ?? 'default',
      input_tokens: request.inputTokens ?? 0,
      output_tokens: request.outputTokens ?? 0,
      attachment_bytes: request.attachmentBytes ?? 0,
      tool_calls: request.toolCalls ?? [],
      selected_data_sources: request.selectedDataSources ?? [],
      async_execution: request.asyncExecution ?? false,
      ...(request.notificationChannel === undefined ? {} : { notification_channel: request.notificationChannel }),
    }))
  }

  async createCheckout(planName: string): Promise<BillingDocument> {
    return this.document('checkout', await this.request('POST', '/billing/create-checkout-session', { plan_name: plan(planName) }))
  }
  async createPaymentLinkCheckout(planName: string): Promise<BillingDocument> {
    return this.document('checkout', await this.request('POST', '/billing/create-payment-link-checkout', { plan_name: plan(planName) }))
  }
  async createPortal(): Promise<BillingDocument> { return this.document('portal', await this.request('POST', '/billing/create-portal-session')) }
  async cancelSubscription(): Promise<BillingDocument> { return this.document('mutation', await this.request('POST', '/billing/cancel-subscription')) }
  async reactivateSubscription(): Promise<BillingDocument> { return this.document('mutation', await this.request('POST', '/billing/reactivate-subscription')) }
}

export default LegacyApiBillingProvider
