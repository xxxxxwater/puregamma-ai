import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import ModelGatewayService, {
  type GatewayCreateKeyRequest,
  type GatewayDocument,
  type GatewayDocumentKind,
  type GatewayJson,
  type GatewayKeyStatus,
  type GatewayRequestHistoryQuery,
  type GatewayTopupRequest,
  type GatewayUsageQuery,
} from '@puregamma/dsh-api-gateway'

export interface Config { baseUrl?: string; authTokenEnv?: string; requestTimeoutMs?: number }
export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(60000).default(15000),
})

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function toJson(value: unknown, path = '$'): GatewayJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`gateway payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const out: Record<string, GatewayJson> = {}
    for (const [key, item] of Object.entries(value)) out[key] = toJson(item, `${path}.${key}`)
    return out
  }
  throw new Error(`gateway payload contains non-JSON value at ${path}`)
}
function toRecord(value: unknown): Record<string, GatewayJson> {
  if (!isRecord(value)) throw new Error('gateway compatibility API returned a non-object payload')
  return toJson(value) as Record<string, GatewayJson>
}
function identifier(value: string, label: string): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > 160 || !/^[A-Za-z0-9._:-]+$/.test(normalized)) throw new Error(`${label} is invalid`)
  return normalized
}
function positiveInt(value: number | undefined, fallback: number, max: number): number {
  if (value === undefined) return fallback
  if (!Number.isInteger(value) || value < 1 || value > max) throw new Error('gateway integer query is out of range')
  return value
}

export class LegacyApiGatewayProvider extends ModelGatewayService {
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
    }, 'pgModelGateway.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness Gateway compatibility provider requires bearer token in ${this.tokenEnv}`)
    return token
  }

  private async request(method: 'GET' | 'POST' | 'DELETE', path: string, body?: unknown, authenticated = true): Promise<Record<string, GatewayJson>> {
    const controller = new AbortController()
    this.controllers.add(controller)
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(new URL(`${this.baseUrl}${path}`), {
        method,
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...(authenticated ? { Authorization: `Bearer ${this.token()}` } : {}),
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      })
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 500)
        throw new Error(`gateway compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      return toRecord(await response.json())
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private document(kind: GatewayDocumentKind, payload: Record<string, GatewayJson>): GatewayDocument {
    return { kind, observedAt: new Date().toISOString(), source: 'compatibility:gateway-api', payload }
  }

  async catalog(): Promise<GatewayDocument> {
    return this.document('catalog', await this.request('GET', '/gateway/catalog', undefined, false))
  }
  async dashboard(): Promise<GatewayDocument> {
    return this.document('dashboard', await this.request('GET', '/gateway/dashboard'))
  }
  async keys(): Promise<GatewayDocument> {
    return this.document('keys', await this.request('GET', '/gateway/keys'))
  }
  async wallet(): Promise<GatewayDocument> {
    return this.document('wallet', await this.request('GET', '/gateway/wallet'))
  }
  async usage(query: GatewayUsageQuery = {}): Promise<GatewayDocument> {
    const url = new URL('/gateway/usage', 'http://puregamma.invalid')
    if (query.start) url.searchParams.set('start', query.start)
    if (query.end) url.searchParams.set('end', query.end)
    url.searchParams.set('granularity', query.granularity ?? 'day')
    if (query.model) url.searchParams.set('model', query.model)
    if (query.apiKeyId) url.searchParams.set('api_key_id', identifier(query.apiKeyId, 'apiKeyId'))
    return this.document('usage', await this.request('GET', `${url.pathname}${url.search}`))
  }
  async requestHistory(query: GatewayRequestHistoryQuery = {}): Promise<GatewayDocument> {
    const params = new URLSearchParams({
      limit: String(positiveInt(query.limit, 50, 200)),
      offset: String(Math.max(0, Math.floor(query.offset ?? 0))),
    })
    return this.document('requests', await this.request('GET', `/gateway/requests?${params}`))
  }
  async createKey(request: GatewayCreateKeyRequest = {}): Promise<GatewayDocument> {
    const name = (request.name ?? 'Default key').trim()
    if (!name || name.length > 80) throw new Error('gateway key name is invalid')
    return this.document('key-mutation', await this.request('POST', '/gateway/keys', {
      name,
      ...(request.rateLimitRpm === undefined ? {} : { rate_limit_rpm: positiveInt(request.rateLimitRpm, 1, 10000) }),
    }))
  }
  async setKeyStatus(keyId: string, status: GatewayKeyStatus): Promise<GatewayDocument> {
    const id = encodeURIComponent(identifier(keyId, 'keyId'))
    if (status === 'revoked') return this.document('key-mutation', await this.request('DELETE', `/gateway/keys/${id}`))
    return this.document('key-mutation', await this.request('POST', `/gateway/keys/${id}/${status === 'paused' ? 'pause' : 'resume'}`))
  }
  async rotateKey(keyId: string): Promise<GatewayDocument> {
    return this.document('key-mutation', await this.request('POST', `/gateway/keys/${encodeURIComponent(identifier(keyId, 'keyId'))}/rotate`))
  }
  async createTopup(request: GatewayTopupRequest): Promise<GatewayDocument> {
    if (!/^\d+(?:\.\d{1,2})?$/.test(request.amountUsd)) throw new Error('gateway top-up amount must be a positive decimal string')
    return this.document('topup', await this.request('POST', '/gateway/topups', { amount_usd: request.amountUsd, locale: request.locale ?? 'en' }))
  }
}

export default LegacyApiGatewayProvider
