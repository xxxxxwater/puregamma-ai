import { Context, Service } from '@deepseek-ai/cordis'

export type OptionsReadKind =
  | 'chain'
  | 'long-gamma'
  | 'surface'
  | 'surface-tickers'
  | 'earnings-gamma'

export type OptionsProviderState = 'healthy' | 'degraded' | 'unavailable'

/** Harness-compatible lossless JSON tree for provider-owned read models. */
export type OptionsJson =
  | null
  | boolean
  | number
  | string
  | OptionsJson[]
  | { [key: string]: OptionsJson }

export interface OptionsDocument {
  kind: OptionsReadKind
  underlying?: string
  provider?: string
  observedAt: string
  state: OptionsProviderState
  /** Options research never grants order execution rights. */
  executionEnabled: false
  source: string
  payload: { [key: string]: OptionsJson }
}

export type OptionsSurfaceType = 'mark_iv' | 'mark_price' | 'gamma' | 'theta' | 'vega' | 'spread_pct'

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgOptions: OptionsService
  }
}

/**
 * Read-only options research seam. Providers may use Deribit, Polygon or a
 * compatibility transport, but execution belongs exclusively to trading
 * services and approval/risk gates.
 */
export abstract class OptionsService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgOptions')
  }

  abstract chain(underlying: string): Promise<OptionsDocument>
  abstract longGamma(underlying: string, limit?: number): Promise<OptionsDocument>
  abstract surface(underlying: string, type?: OptionsSurfaceType): Promise<OptionsDocument>
  abstract surfaceTickers(): Promise<OptionsDocument>
  abstract earningsGamma(language?: 'en' | 'zh'): Promise<OptionsDocument>
}

export default OptionsService
