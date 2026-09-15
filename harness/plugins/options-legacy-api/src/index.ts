import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import OptionsService, {
  type OptionsDocument,
  type OptionsJson,
  type OptionsProviderState,
  type OptionsReadKind,
  type OptionsSurfaceType,
} from '@puregamma/dsh-options'

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

const SURFACE_TYPES = new Set<OptionsSurfaceType>(['mark_iv', 'mark_price', 'gamma', 'theta', 'vega', 'spread_pct'])

function trimSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toOptionsJson(value: unknown, path = '$'): OptionsJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`options compatibility payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toOptionsJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const output: Record<string, OptionsJson> = {}
    for (const [key, item] of Object.entries(value)) output[key] = toOptionsJson(item, `${path}.${key}`)
    return output
  }
  throw new Error(`options compatibility payload contains non-JSON value at ${path}`)
}

function toOptionsRecord(value: unknown): Record<string, OptionsJson> {
  if (!isRecord(value)) throw new Error('options compatibility API returned a non-object payload')
  return toOptionsJson(value) as Record<string, OptionsJson>
}

function stringField(payload: Record<string, OptionsJson>, key: string): string | undefined {
  const value = payload[key]
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined
}

function providerState(payload: Record<string, OptionsJson>): OptionsProviderState {
  const status = stringField(payload, 'status')?.toLowerCase()
  if (status === undefined || status === 'healthy' || status === 'ok') return 'healthy'
  if (status === 'degraded' || status === 'partial') return 'degraded'
  return 'unavailable'
}

function validObservedAt(value: string | undefined): string | undefined {
  if (value === undefined) return undefined
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : undefined
}

function normalizeUnderlying(value: string): string {
  const normalized = value.trim().toUpperCase()
  if (!/^[A-Z0-9._-]{1,24}$/.test(normalized)) throw new Error('underlying must be a 1-24 character market symbol')
  return normalized
}

function normalizeLimit(value: number): number {
  if (!Number.isInteger(value) || value < 1 || value > 25) throw new Error('limit must be an integer between 1 and 25')
  return value
}

function normalizeSurfaceType(value: OptionsSurfaceType): OptionsSurfaceType {
  if (!SURFACE_TYPES.has(value)) throw new Error(`unsupported options surface type: ${value}`)
  return value
}

function hasVerifiedEarningsDate(value: unknown): boolean {
  if (!isRecord(value)) return false
  const raw = value.earnings_date
  if (typeof raw !== 'string' || raw.trim().length === 0) return false
  const timestamp = Date.parse(`${raw.trim()}T00:00:00Z`)
  return Number.isFinite(timestamp)
}

/**
 * Legacy earnings-gamma can fall back to a static symbol list with blank dates.
 * That is UI scaffolding, not evidence. Keep the feature surface but remove such
 * placeholder candidates at the migration boundary and explicitly degrade it.
 */
function sanitizeEarningsGamma(payload: Record<string, OptionsJson>): Record<string, OptionsJson> {
  const rawCandidates = payload.candidates
  if (!Array.isArray(rawCandidates)) return payload
  const verified = rawCandidates.filter(hasVerifiedEarningsDate)
  const removed = rawCandidates.length - verified.length
  if (removed === 0) return payload
  return {
    ...payload,
    status: 'DEGRADED',
    candidates: verified as OptionsJson[],
    migration_health: {
      status: 'degraded',
      reason: 'placeholder_earnings_candidates_removed',
      removed,
    },
  }
}

/**
 * Temporary compatibility provider for legacy read-only options endpoints.
 * The stable capability is ctx.pgOptions. This plugin never exposes order
 * submission, and every returned document hard-codes executionEnabled=false.
 */
export class LegacyApiOptionsProvider extends OptionsService {
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

  private async request(path: string, query: Record<string, string | number | undefined> = {}): Promise<Record<string, OptionsJson>> {
    const token = process.env[this.tokenEnv]
    if (token === undefined || token.length === 0) {
      throw new Error(`PureGamma Harness options compatibility provider requires bearer token in ${this.tokenEnv}`)
    }
    const url = new URL(`${this.baseUrl}${path}`)
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
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
      if (!response.ok) throw new Error(`options compatibility API returned HTTP ${response.status} for ${path}`)
      return toOptionsRecord(await response.json())
    } finally {
      clearTimeout(timer)
    }
  }

  private document(kind: OptionsReadKind, payload: Record<string, OptionsJson>, underlying?: string): OptionsDocument {
    return {
      kind,
      ...(underlying === undefined ? {} : { underlying }),
      ...(stringField(payload, 'provider') === undefined ? {} : { provider: stringField(payload, 'provider') }),
      observedAt: validObservedAt(stringField(payload, 'fetched_at')) ?? new Date().toISOString(),
      state: providerState(payload),
      executionEnabled: false,
      source: 'compatibility:options-api',
      payload,
    }
  }

  async chain(underlying: string): Promise<OptionsDocument> {
    const symbol = normalizeUnderlying(underlying)
    return this.document('chain', await this.request('/options/chain', { currency: symbol }), symbol)
  }

  async longGamma(underlying: string, limit = 10): Promise<OptionsDocument> {
    const symbol = normalizeUnderlying(underlying)
    return this.document('long-gamma', await this.request('/options/long-gamma', {
      currency: symbol,
      limit: normalizeLimit(limit),
    }), symbol)
  }

  async surface(underlying: string, type: OptionsSurfaceType = 'mark_iv'): Promise<OptionsDocument> {
    const symbol = normalizeUnderlying(underlying)
    return this.document('surface', await this.request('/options/surface', {
      currency: symbol,
      type: normalizeSurfaceType(type),
    }), symbol)
  }

  async surfaceTickers(): Promise<OptionsDocument> {
    return this.document('surface-tickers', await this.request('/options/surface-tickers'))
  }

  async earningsGamma(language: 'en' | 'zh' = 'en'): Promise<OptionsDocument> {
    const payload = sanitizeEarningsGamma(await this.request('/options/earnings-gamma', { language }))
    return this.document('earnings-gamma', payload)
  }
}

export default LegacyApiOptionsProvider
