import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import DataSourcesService, {
  type DataSourceDocument,
  type DataSourceDocumentKind,
  type DataSourceJson,
  type FinTwitAccountUpdate,
} from '@puregamma/dsh-data-sources'

export interface Config { baseUrl?: string; authTokenEnv?: string; requestTimeoutMs?: number }
export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(120000).default(30000),
})

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function toJson(value: unknown, path = '$'): DataSourceJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`data-source payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const out: Record<string, DataSourceJson> = {}
    for (const [key, item] of Object.entries(value)) out[key] = toJson(item, `${path}.${key}`)
    return out
  }
  throw new Error(`data-source payload contains non-JSON value at ${path}`)
}
function toRecord(value: unknown): Record<string, DataSourceJson> {
  if (!isRecord(value)) throw new Error('data-source compatibility API returned a non-object payload')
  return toJson(value) as Record<string, DataSourceJson>
}
function identifier(value: string, label: string): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > 160 || !/^[A-Za-z0-9._:-]+$/.test(normalized)) throw new Error(`${label} is invalid`)
  return normalized
}
function bounded(value: number | undefined, min: number, max: number, label: string): number | undefined {
  if (value === undefined) return undefined
  if (!Number.isFinite(value) || value < min || value > max) throw new Error(`${label} is out of range`)
  return value
}

export class LegacyApiDataSourcesProvider extends DataSourcesService {
  static Config = Config
  private readonly baseUrl: string
  private readonly tokenEnv: string
  private readonly timeoutMs: number
  private readonly controllers = new Set<AbortController>()

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.tokenEnv = config.authTokenEnv ?? 'PUREGAMMA_LEGACY_API_TOKEN'
    this.timeoutMs = config.requestTimeoutMs ?? 30000
    ctx.effect(() => () => {
      for (const controller of this.controllers) controller.abort()
      this.controllers.clear()
    }, 'pgDataSources.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness data-source compatibility provider requires admin bearer token in ${this.tokenEnv}`)
    return token
  }

  private async request(method: 'GET' | 'POST' | 'PATCH', path: string, body?: unknown): Promise<Record<string, DataSourceJson>> {
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
        throw new Error(`data-source compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      return toRecord(await response.json())
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private document(kind: DataSourceDocumentKind, payload: Record<string, DataSourceJson>): DataSourceDocument {
    return { kind, observedAt: new Date().toISOString(), source: 'compatibility:admin-data-sources-api', payload }
  }

  async catalog(): Promise<DataSourceDocument> { return this.document('catalog', await this.request('GET', '/admin/data-sources')) }
  async health(): Promise<DataSourceDocument> { return this.document('health', await this.request('GET', '/admin/data-sources/health')) }
  async preview(providerId: string): Promise<DataSourceDocument> {
    return this.document('preview', await this.request('GET', `/admin/data-sources/${encodeURIComponent(identifier(providerId, 'providerId'))}/preview`))
  }
  async runs(providerId: string): Promise<DataSourceDocument> {
    return this.document('runs', await this.request('GET', `/admin/data-sources/${encodeURIComponent(identifier(providerId, 'providerId'))}/runs`))
  }
  async fintwitAccounts(): Promise<DataSourceDocument> {
    return this.document('fintwit-accounts', await this.request('GET', '/admin/data-sources/fintwit/accounts'))
  }
  async setEnabled(providerId: string, enabled: boolean): Promise<DataSourceDocument> {
    return this.document('mutation', await this.request('PATCH', `/admin/data-sources/${encodeURIComponent(identifier(providerId, 'providerId'))}`, { enabled }))
  }
  async checkConfig(providerId: string): Promise<DataSourceDocument> {
    return this.document('mutation', await this.request('POST', `/admin/data-sources/${encodeURIComponent(identifier(providerId, 'providerId'))}/config-check`))
  }
  async sync(providerId: string): Promise<DataSourceDocument> {
    return this.document('sync', await this.request('POST', `/admin/data-sources/${encodeURIComponent(identifier(providerId, 'providerId'))}/sync`))
  }
  async syncAll(): Promise<DataSourceDocument> {
    return this.document('sync', await this.request('POST', '/admin/data-sources/sync-all'))
  }
  async updateFintwitAccount(accountId: string, update: FinTwitAccountUpdate): Promise<DataSourceDocument> {
    const credibility = bounded(update.credibilityScore, 0, 1, 'credibilityScore')
    const weight = bounded(update.accountWeight, 0, 2, 'accountWeight')
    return this.document('mutation', await this.request('PATCH', `/admin/data-sources/fintwit/accounts/${encodeURIComponent(identifier(accountId, 'accountId'))}`, {
      ...(update.enabled === undefined ? {} : { enabled: update.enabled }),
      ...(credibility === undefined ? {} : { credibility_score: credibility }),
      ...(weight === undefined ? {} : { account_weight: weight }),
      ...(update.providerUserId === undefined ? {} : { provider_user_id: update.providerUserId }),
    }))
  }
}

export default LegacyApiDataSourcesProvider
