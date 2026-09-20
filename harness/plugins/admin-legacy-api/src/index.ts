import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import AdminService, {
  type AdminDocument,
  type AdminDocumentKind,
  type AdminJson,
  type AdminListQuery,
} from '@puregamma/dsh-admin'

export interface Config { baseUrl?: string; authTokenEnv?: string; requestTimeoutMs?: number }
export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(60000).default(15000),
})

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function toJson(value: unknown, path = '$'): AdminJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`admin payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const out: Record<string, AdminJson> = {}
    for (const [key, item] of Object.entries(value)) out[key] = toJson(item, `${path}.${key}`)
    return out
  }
  throw new Error(`admin payload contains non-JSON value at ${path}`)
}
function toRecord(value: unknown): Record<string, AdminJson> {
  if (!isRecord(value)) throw new Error('admin compatibility API returned a non-object payload')
  return toJson(value) as Record<string, AdminJson>
}
function identifier(value: string, label: string): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > 160 || !/^[A-Za-z0-9._:-]+$/.test(normalized)) throw new Error(`${label} is invalid`)
  return normalized
}
function listPath(path: string, query: AdminListQuery = {}): string {
  const params = new URLSearchParams()
  if (query.limit !== undefined) params.set('limit', String(Math.min(100, Math.max(1, Math.floor(query.limit)))))
  if (query.offset !== undefined) params.set('offset', String(Math.max(0, Math.floor(query.offset))))
  if (query.status) params.set('status', query.status.slice(0, 40))
  if (query.userId) params.set('user_id', identifier(query.userId, 'userId'))
  const suffix = params.toString()
  return suffix ? `${path}?${suffix}` : path
}

export class LegacyApiAdminProvider extends AdminService {
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
    }, 'pgAdmin.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness admin compatibility provider requires admin bearer token in ${this.tokenEnv}`)
    return token
  }

  private async get(path: string): Promise<Record<string, AdminJson>> {
    const controller = new AbortController()
    this.controllers.add(controller)
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(new URL(`${this.baseUrl}${path}`), {
        method: 'GET', signal: controller.signal,
        headers: { Accept: 'application/json', Authorization: `Bearer ${this.token()}` },
      })
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 500)
        throw new Error(`admin compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      return toRecord(await response.json())
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private async document(kind: AdminDocumentKind, path: string): Promise<AdminDocument> {
    return { kind, observedAt: new Date().toISOString(), source: 'compatibility:admin-api', payload: await this.get(path) }
  }

  overview(): Promise<AdminDocument> { return this.document('overview', '/admin/overview') }
  systemStatus(): Promise<AdminDocument> { return this.document('system-status', '/admin/system-status') }
  llmStatus(): Promise<AdminDocument> { return this.document('llm-status', '/admin/llm-status') }
  llmCostSummary(): Promise<AdminDocument> { return this.document('llm-cost-summary', '/admin/llm-cost-summary') }
  agentRuns(): Promise<AdminDocument> { return this.document('agent-runs', '/admin/agent/runs') }
  agentRun(runId: string): Promise<AdminDocument> { return this.document('agent-run', `/admin/agent/runs/${encodeURIComponent(identifier(runId, 'runId'))}`) }
  reports(query: AdminListQuery = {}): Promise<AdminDocument> { return this.document('reports', listPath('/admin/reports', query)) }
  deliveries(query: AdminListQuery = {}): Promise<AdminDocument> { return this.document('deliveries', listPath('/admin/deliveries', query)) }
  alerts(query: AdminListQuery = {}): Promise<AdminDocument> { return this.document('alerts', listPath('/admin/alerts', query)) }
  skillRuns(query: AdminListQuery = {}): Promise<AdminDocument> { return this.document('skill-runs', listPath('/admin/skill-runs', query)) }
  portfolioSync(query: AdminListQuery = {}): Promise<AdminDocument> { return this.document('portfolio-sync', listPath('/admin/portfolio-sync', query)) }
  backtests(query: AdminListQuery = {}): Promise<AdminDocument> { return this.document('backtests', listPath('/admin/backtests', query)) }
  trading(query: AdminListQuery = {}): Promise<AdminDocument> { return this.document('trading', listPath('/admin/trading', query)) }
  stripeSummary(): Promise<AdminDocument> { return this.document('stripe-summary', '/admin/stripe/summary') }
}

export default LegacyApiAdminProvider
