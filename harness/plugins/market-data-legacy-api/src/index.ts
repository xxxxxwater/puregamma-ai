import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import MarketDataService, {
  type MarketInstrument,
  type MarketNewsItem,
  type MarketQuote,
  type MarketSnapshot,
  type ProviderHealth,
} from '@puregamma/dsh-market-data'

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

interface LegacyAsset {
  symbol?: unknown
  price?: unknown
  volume_24h?: unknown
  timestamp?: unknown
  source?: unknown
  is_realtime?: unknown
  asset_type?: unknown
}

interface LegacySnapshot {
  assets?: unknown
}

interface LegacyNewsItem {
  id?: unknown
  provider?: unknown
  source?: unknown
  title?: unknown
  summary?: unknown
  url?: unknown
  published_at?: unknown
  symbols?: unknown
  language?: unknown
}

interface LegacyNewsResponse {
  items?: unknown
}

function trimSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function asString(value: unknown): string | undefined {
  if (typeof value === 'string' && value.length > 0) return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return undefined
}

function assetClass(value: unknown): MarketInstrument['assetClass'] {
  switch (String(value ?? '').toLowerCase()) {
    case 'equity': return 'equity'
    case 'option': return 'option'
    case 'fx':
    case 'forex': return 'fx'
    case 'rate':
    case 'rates': return 'rate'
    case 'commodity':
    case 'metal':
    case 'energy': return 'commodity'
    default: return 'crypto'
  }
}

function isStale(timestamp: string, realtime: boolean, maxAgeMs?: number): boolean {
  if (!realtime) return true
  if (maxAgeMs === undefined) return false
  const observed = Date.parse(timestamp)
  return !Number.isFinite(observed) || Date.now() - observed > maxAgeMs
}

/**
 * Migration-only provider. It lets Harness consumers move first while the
 * existing FastAPI/data implementation is still the source of truth.
 * The dependency is deliberately one-way and this package is deleted once
 * native Harness providers replace the old API.
 */
export class LegacyApiMarketDataProvider extends MarketDataService {
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

  private async requestJson(path: string, init: RequestInit = {}): Promise<unknown> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(`${this.baseUrl}${path}`, { ...init, signal: controller.signal })
      if (!response.ok) {
        throw new Error(`legacy PureGamma API ${path} returned HTTP ${response.status}`)
      }
      return await response.json()
    } finally {
      clearTimeout(timer)
    }
  }

  private async allQuotes(maxAgeMs?: number): Promise<MarketQuote[]> {
    const payload = await this.requestJson('/market/snapshot') as LegacySnapshot
    if (!Array.isArray(payload.assets)) {
      throw new Error('legacy PureGamma /market/snapshot returned no assets array')
    }
    const quotes: MarketQuote[] = []
    for (const raw of payload.assets as LegacyAsset[]) {
      const symbol = asString(raw.symbol)
      const last = asString(raw.price)
      const observedAt = asString(raw.timestamp)
      const source = asString(raw.source)
      if (symbol === undefined || last === undefined || observedAt === undefined || source === undefined) continue
      const realtime = raw.is_realtime === true
      quotes.push({
        instrument: {
          venue: source,
          symbol: symbol.toUpperCase(),
          assetClass: assetClass(raw.asset_type),
        },
        last,
        volume24h: asString(raw.volume_24h),
        observedAt,
        source,
        stale: isStale(observedAt, realtime, maxAgeMs),
      })
    }
    return quotes
  }

  async snapshot(instruments: readonly MarketInstrument[], maxAgeMs?: number): Promise<MarketSnapshot> {
    const all = await this.allQuotes(maxAgeMs)
    const wanted = new Set(instruments.map(item => item.symbol.toUpperCase()))
    const quotes = wanted.size === 0 ? all : all.filter(item => wanted.has(item.instrument.symbol.toUpperCase()))
    const times = quotes.map(item => Date.parse(item.observedAt)).filter(Number.isFinite)
    return {
      quotes,
      asOf: times.length === 0 ? new Date().toISOString() : new Date(Math.max(...times)).toISOString(),
    }
  }

  async quote(instrument: MarketInstrument, maxAgeMs?: number): Promise<MarketQuote | undefined> {
    const result = await this.snapshot([instrument], maxAgeMs)
    return result.quotes.find(item => item.instrument.symbol.toUpperCase() === instrument.symbol.toUpperCase())
  }

  async news(query: { symbols?: readonly string[]; limit?: number; since?: string }): Promise<readonly MarketNewsItem[]> {
    const token = process.env[this.tokenEnv]
    if (token === undefined || token.length === 0) {
      throw new Error(`legacy news requires bearer token in ${this.tokenEnv}`)
    }
    const params = new URLSearchParams()
    params.set('limit', String(Math.min(Math.max(query.limit ?? 30, 1), 50)))
    const firstSymbol = query.symbols?.[0]
    if (firstSymbol !== undefined) params.set('symbol', firstSymbol)
    if (query.since !== undefined) {
      const since = Date.parse(query.since)
      if (Number.isFinite(since)) {
        const hours = Math.ceil(Math.max(1, Date.now() - since) / 3_600_000)
        params.set('hours', String(Math.min(hours, 168)))
      }
    }
    const payload = await this.requestJson(`/api/news?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
    }) as LegacyNewsResponse
    if (!Array.isArray(payload.items)) throw new Error('legacy PureGamma /api/news returned no items array')
    return (payload.items as LegacyNewsItem[]).flatMap((raw): MarketNewsItem[] => {
      const id = asString(raw.id)
      const title = asString(raw.title)
      const publishedAt = asString(raw.published_at)
      if (id === undefined || title === undefined || publishedAt === undefined) return []
      return [{
        id,
        source: asString(raw.provider) ?? asString(raw.source) ?? 'legacy-puregammma',
        title,
        summary: asString(raw.summary),
        url: asString(raw.url),
        publishedAt,
        symbols: Array.isArray(raw.symbols) ? raw.symbols.filter((value): value is string => typeof value === 'string') : undefined,
        language: asString(raw.language),
      }]
    })
  }

  async health(): Promise<readonly ProviderHealth[]> {
    const observedAt = new Date().toISOString()
    let market: ProviderHealth
    try {
      await this.requestJson('/health')
      market = { provider: 'legacy-puregamma-api', state: 'healthy', observedAt }
    } catch (error) {
      market = {
        provider: 'legacy-puregamma-api',
        state: 'unavailable',
        observedAt,
        detail: error instanceof Error ? error.message : String(error),
      }
    }
    const token = process.env[this.tokenEnv]
    const news: ProviderHealth = token
      ? { provider: 'legacy-puregamma-news', state: market.state, observedAt, detail: market.detail }
      : { provider: 'legacy-puregamma-news', state: 'unavailable', observedAt, detail: `missing ${this.tokenEnv}` }
    return [market, news]
  }
}

export default LegacyApiMarketDataProvider
