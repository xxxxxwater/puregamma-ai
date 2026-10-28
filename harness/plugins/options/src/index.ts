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
/**
 * Client presentation of one options read, persisted as the tool result's
 * `meta` (never model-visible): provenance, provider state and size only.
 */
export interface OptionsDocumentPresentation {
  readonly schema: 'puregamma.options.document/v1'
  readonly kind: OptionsReadKind
  readonly underlying: string | null
  readonly provider: string | null
  readonly observedAt: string
  readonly state: OptionsProviderState
  readonly executionEnabled: false
  readonly source: string
  /** Rows in the largest list the payload carried (chain rows, candidates); null when none. */
  readonly size: number | null
}

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
