import { Context, Service } from '@deepseek-ai/cordis'

export type AssetClass = 'crypto' | 'equity' | 'option' | 'fx' | 'rate' | 'commodity'

export interface MarketInstrument {
  venue: string
  symbol: string
  assetClass: AssetClass
}

export interface MarketQuote {
  instrument: MarketInstrument
  bid?: string
  ask?: string
  last?: string
  mark?: string
  volume24h?: string
  observedAt: string
  source: string
  stale: boolean
}

export interface MarketNewsItem {
  id: string
  source: string
  title: string
  summary?: string
  url?: string
  publishedAt: string
  symbols?: readonly string[]
  language?: string
}

export interface ProviderHealth {
  provider: string
  state: 'starting' | 'healthy' | 'degraded' | 'unavailable'
  observedAt: string
  detail?: string
}

export interface MarketSnapshot {
  quotes: readonly MarketQuote[]
  asOf: string
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgMarketData: MarketDataService
  }
}

/**
 * Read-only market-data seam. Concrete providers own exchange/vendor details;
 * consumers see only normalized, timestamped, provenance-carrying data.
 */
export abstract class MarketDataService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgMarketData')
  }

  abstract snapshot(instruments: readonly MarketInstrument[], maxAgeMs?: number): Promise<MarketSnapshot>
  abstract quote(instrument: MarketInstrument, maxAgeMs?: number): Promise<MarketQuote | undefined>
  abstract news(query: { symbols?: readonly string[]; limit?: number; since?: string }): Promise<readonly MarketNewsItem[]>
  abstract health(): Promise<readonly ProviderHealth[]>
}

export default MarketDataService
