import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import ResearchService, {
  type ResearchDocument,
  type ResearchJson,
  type ResearchKind,
} from '@puregamma/dsh-research'

export interface Config {
  baseUrl?: string
  authTokenEnv?: string
  requestTimeoutMs?: number
}

export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(60000).default(10000),
})

function trimSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toResearchJson(value: unknown, path = '$'): ResearchJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`research compatibility payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) {
    return value.map((item, index) => toResearchJson(item, `${path}[${index}]`))
  }
  if (isRecord(value)) {
    const output: Record<string, ResearchJson> = {}
    for (const [key, item] of Object.entries(value)) output[key] = toResearchJson(item, `${path}.${key}`)
    return output
  }
  throw new Error(`research compatibility payload contains non-JSON value at ${path}`)
}

function toResearchRecord(value: unknown): Record<string, ResearchJson> {
  if (!isRecord(value)) throw new Error('research compatibility API returned a non-object payload')
  return toResearchJson(value) as Record<string, ResearchJson>
}

function stringField(record: Record<string, ResearchJson>, key: string): string | undefined {
  const value = record[key]
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined
}

function healthIsDegraded(payload: Record<string, ResearchJson>): boolean {
  const health = payload.health
  if (!isRecord(health)) return false

  const overall = health.overall
  if (typeof overall === 'string') {
    const normalized = overall.trim().toLowerCase()
    if (normalized !== 'ok' && normalized !== 'healthy') return true
  }

  for (const value of Object.values(health)) {
    if (!isRecord(value)) continue
    const status = value.status
    if (typeof status !== 'string') continue
    const normalized = status.trim().toLowerCase()
    if (normalized !== 'ok' && normalized !== 'healthy') return true
  }
  return false
}

function assertIntegerRange(value: number, min: number, max: number, label: string): number {
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new Error(`${label} must be an integer between ${min} and ${max}`)
  }
  return value
}

/**
 * Migration-only provider for the legacy PureGamma research read models.
 *
 * FastAPI is treated strictly as a temporary compatibility transport. The
 * durable contract is ctx.pgResearch; native evidence stores and research
 * providers can replace this plugin without changing consumers or model tools.
 */
export class LegacyApiResearchProvider extends ResearchService {
  static Config = Config

  private readonly baseUrl: string
  private readonly tokenEnv: string
  private readonly timeoutMs: number

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.tokenEnv = config.authTokenEnv ?? 'PUREGAMMA_LEGACY_API_TOKEN'
    this.timeoutMs = config.requestTimeoutMs ?? 10000
  }

  private async request(path: string, query: Record<string, string | number | undefined> = {}): Promise<Record<string, ResearchJson>> {
    const token = process.env[this.tokenEnv]
    if (token === undefined || token.length === 0) {
      throw new Error(`PureGamma Harness research compatibility provider requires bearer token in ${this.tokenEnv}`)
    }

    const url = new URL(`${this.baseUrl}${path}`)
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined) continue
      url.searchParams.set(key, String(value))
    }

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${token}`,
        },
      })
      if (!response.ok) throw new Error(`research compatibility API returned HTTP ${response.status} for ${path}`)
      return toResearchRecord(await response.json())
    } finally {
      clearTimeout(timer)
    }
  }

  private document(kind: ResearchKind, payload: Record<string, ResearchJson>): ResearchDocument {
    const asOf = stringField(payload, 'as_of')
    return {
      kind,
      ...(asOf === undefined ? {} : { asOf }),
      observedAt: new Date().toISOString(),
      degraded: healthIsDegraded(payload),
      source: 'compatibility:research-api',
      payload,
    }
  }

  async today(locale?: string): Promise<ResearchDocument> {
    const normalizedLocale = locale?.trim() || undefined
    return this.document('today', await this.request('/research/today', { locale: normalizedLocale }))
  }

  async overnight(sinceHours = 14): Promise<ResearchDocument> {
    const value = assertIntegerRange(sinceHours, 1, 72, 'sinceHours')
    return this.document('overnight', await this.request('/research/overnight', { since_hours: value }))
  }

  async portfolioImpact(): Promise<ResearchDocument> {
    return this.document('portfolio-impact', await this.request('/research/portfolio/impact'))
  }

  async upcomingEvents(days = 14): Promise<ResearchDocument> {
    const value = assertIntegerRange(days, 1, 60, 'days')
    return this.document('upcoming-events', await this.request('/research/events/upcoming', { days: value }))
  }

  async opportunities(locale?: string): Promise<ResearchDocument> {
    const normalizedLocale = locale?.trim() || undefined
    return this.document('opportunities', await this.request('/research/opportunities', { locale: normalizedLocale }))
  }

  async alerts(): Promise<ResearchDocument> {
    return this.document('alerts', await this.request('/research/alerts'))
  }
}

export default LegacyApiResearchProvider
