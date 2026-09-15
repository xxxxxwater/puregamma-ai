import { Context, Service } from '@deepseek-ai/cordis'

export type BacktestJson =
  | null
  | boolean
  | number
  | string
  | BacktestJson[]
  | { [key: string]: BacktestJson }

export type BacktestDocumentKind =
  | 'status'
  | 'spec'
  | 'run'
  | 'runs'
  | 'artifact'
  | 'strategy'
  | 'data-status'

export interface BacktestDocument {
  kind: BacktestDocumentKind
  observedAt: string
  source: string
  payload: { [key: string]: BacktestJson }
}

export interface BacktestCompileRequest {
  idea: string
  useMemory?: boolean
  locale?: 'en' | 'zh'
}

export interface BacktestRunRequest {
  spec: { [key: string]: BacktestJson }
  windowDays?: number
  /** Required by Harness so retried tool calls cannot create duplicate billable runs. */
  idempotencyKey: string
  contextMeta?: { [key: string]: BacktestJson }
}

export interface BacktestRunListRequest {
  limit?: number
  offset?: number
}

export type BacktestExportFormat = 'json' | 'csv'

export interface BacktestTerminalEvent {
  sequence?: number
  type: string
  line?: string
  payload: { [key: string]: BacktestJson }
}

export interface BacktestArtifactBinary {
  contentType: string
  fileName?: string
  bytes: Uint8Array
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgBacktest: BacktestService
  }
}

/**
 * Stateful backtest seam. Billing/entitlement enforcement remains provider-side,
 * while idempotency and lifecycle semantics are part of the stable Harness
 * contract. Streaming resources must be cleanup-aware on plugin unload.
 */
export abstract class BacktestService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgBacktest')
  }

  abstract status(): Promise<BacktestDocument>
  abstract compile(request: BacktestCompileRequest): Promise<BacktestDocument>
  abstract run(request: BacktestRunRequest): Promise<BacktestDocument>
  abstract listRuns(request?: BacktestRunListRequest): Promise<BacktestDocument>
  abstract result(runId: string): Promise<BacktestDocument>
  abstract cancel(runId: string): Promise<BacktestDocument>
  abstract exportRun(runId: string, format?: BacktestExportFormat): Promise<BacktestDocument>
  abstract saveAsStrategy(runId: string): Promise<BacktestDocument>
  abstract refreshData(): Promise<BacktestDocument>
  abstract terminalEvents(runId: string, afterSequence?: number): AsyncIterable<BacktestTerminalEvent>
  abstract artifact(artifactId: string): Promise<BacktestArtifactBinary>
}

export default BacktestService
