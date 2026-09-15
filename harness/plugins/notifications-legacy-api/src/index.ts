import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import NotificationsService, {
  type DailyBriefUpdate,
  type NotificationDocument,
  type NotificationDocumentKind,
  type NotificationJson,
  type NotificationSendRequest,
  type PushDeviceRequest,
} from '@puregamma/dsh-notifications'

export interface Config { baseUrl?: string; authTokenEnv?: string; requestTimeoutMs?: number }
export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(60000).default(15000),
})

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function toJson(value: unknown, path = '$'): NotificationJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`notification payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const out: Record<string, NotificationJson> = {}
    for (const [key, item] of Object.entries(value)) out[key] = toJson(item, `${path}.${key}`)
    return out
  }
  throw new Error(`notification payload contains non-JSON value at ${path}`)
}
function toRecord(value: unknown): Record<string, NotificationJson> {
  if (!isRecord(value)) throw new Error('notification compatibility API returned a non-object payload')
  return toJson(value) as Record<string, NotificationJson>
}
function safeText(value: string, label: string, max: number): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > max) throw new Error(`${label} is invalid`)
  return normalized
}
function idem(value: string): string {
  const normalized = value.trim()
  if (normalized.length < 8 || normalized.length > 160 || !/^[A-Za-z0-9._:-]+$/.test(normalized)) throw new Error('notification idempotency key is invalid')
  return normalized
}

export class LegacyApiNotificationsProvider extends NotificationsService {
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
    }, 'pgNotifications.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness notifications compatibility provider requires bearer token in ${this.tokenEnv}`)
    return token
  }

  private async request(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown): Promise<Record<string, NotificationJson>> {
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
        throw new Error(`notifications compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      return toRecord(await response.json())
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private document(kind: NotificationDocumentKind, payload: Record<string, NotificationJson>): NotificationDocument {
    return { kind, observedAt: new Date().toISOString(), source: 'compatibility:notifications-api', payload }
  }

  async devices(): Promise<NotificationDocument> { return this.document('devices', await this.request('GET', '/notifications/devices')) }
  async registerDevice(request: PushDeviceRequest): Promise<NotificationDocument> {
    return this.document('devices', await this.request('POST', '/notifications/devices', {
      token: safeText(request.token, 'push token', 256),
      environment: request.environment ?? 'production',
      locale: request.locale ?? 'en',
      timezone: request.timezone ?? 'UTC',
    }))
  }
  async unregisterDevice(request: PushDeviceRequest): Promise<NotificationDocument> {
    return this.document('mutation', await this.request('POST', '/notifications/devices/unregister', {
      token: safeText(request.token, 'push token', 256),
      environment: request.environment ?? 'production', locale: request.locale ?? 'en', timezone: request.timezone ?? 'UTC',
    }))
  }
  async imessageConfig(): Promise<NotificationDocument> { return this.document('imessage-config', await this.request('GET', '/notifications/imessage/config')) }
  async requestImessageVerification(recipient: string): Promise<NotificationDocument> {
    return this.document('verification', await this.request('POST', '/notifications/imessage/verify/request', { recipient: safeText(recipient, 'iMessage recipient', 160) }))
  }
  async confirmImessageVerification(challengeId: string, code: string): Promise<NotificationDocument> {
    return this.document('verification', await this.request('POST', '/notifications/imessage/verify/confirm', { challenge_id: safeText(challengeId, 'challenge id', 160), code: safeText(code, 'verification code', 32) }))
  }
  async testImessage(): Promise<NotificationDocument> { return this.document('delivery', await this.request('POST', '/notifications/imessage/test')) }
  async dailyBrief(): Promise<NotificationDocument> { return this.document('daily-brief', await this.request('GET', '/notifications/preferences/daily-brief')) }
  async updateDailyBrief(request: DailyBriefUpdate): Promise<NotificationDocument> {
    return this.document('daily-brief', await this.request('PUT', '/notifications/preferences/daily-brief', {
      ...(request.enabled === undefined ? {} : { enabled: request.enabled }),
      ...(request.timezone === undefined ? {} : { timezone: request.timezone }),
      ...(request.localTime === undefined ? {} : { local_time: request.localTime }),
      ...(request.channel === undefined ? {} : { channel: request.channel }),
      ...(request.channels === undefined ? {} : { channels: request.channels }),
      ...(request.reportTypes === undefined ? {} : { report_types: request.reportTypes }),
      ...(request.locale === undefined ? {} : { locale: request.locale }),
      ...(request.includePortfolio === undefined ? {} : { include_portfolio: request.includePortfolio }),
      ...(request.includeMarket === undefined ? {} : { include_market: request.includeMarket }),
      ...(request.includeSignals === undefined ? {} : { include_signals: request.includeSignals }),
      ...(request.includeRisk === undefined ? {} : { include_risk: request.includeRisk }),
      ...(request.includeSentiment === undefined ? {} : { include_sentiment: request.includeSentiment }),
      ...(request.quietHours === undefined ? {} : { quiet_hours: request.quietHours }),
      ...(request.maxLength === undefined ? {} : { max_length: request.maxLength }),
    }))
  }
  async send(request: NotificationSendRequest): Promise<NotificationDocument> {
    const message = safeText(request.message, 'notification message', 10000)
    return this.document('delivery', await this.request('POST', '/notifications/send', {
      channel: request.channel,
      message,
      locale: request.locale,
      metadata: { ...(request.metadata ?? {}), idempotency_key: idem(request.idempotencyKey) },
    }))
  }
  async deliveries(channel?: string): Promise<NotificationDocument> {
    const suffix = channel?.trim() ? `?channel=${encodeURIComponent(channel.trim())}` : ''
    return this.document('deliveries', await this.request('GET', `/notifications/deliveries${suffix}`))
  }
}

export default LegacyApiNotificationsProvider
