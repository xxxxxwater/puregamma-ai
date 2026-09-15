import { Context, Service } from '@deepseek-ai/cordis'

export type PgTsyRunMode = 'shadow' | 'paper' | 'live' | 'unknown'

export interface PgTsyRuntimeSnapshot {
  processHealthy: boolean
  ready: boolean
  mode: PgTsyRunMode
  leaseHealthy: boolean
  feedsTotal: number
  feedsConnected: number
  eventsTotal: number
  policyDecisionsTotal: number
  openOrders: number
  ordersJournaledTotal: number
  blockingGates: readonly string[]
  lastError?: string
  observedAt: string
  source: string
}

export interface PgTsyControlAck {
  accepted: boolean
  command: string
  reason?: string
  observedAt: string
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgTsyRuntime: PgTsyRuntimeService
  }
}

/**
 * Stable Cordis seam for the external Rust pg-tsy runtime.
 *
 * Consumers never import pg-tsy crates, Docker details or HTTP endpoints.
 * The provider is replaceable and may supervise a local process, Docker
 * container, Kubernetes workload or remote runtime as long as this contract is
 * preserved. Money-moving operations are deliberately NOT part of this seam;
 * those remain behind the dedicated execution/risk/approval services.
 */
export abstract class PgTsyRuntimeService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgTsyRuntime')
  }

  abstract health(): Promise<PgTsyRuntimeSnapshot>
  abstract ready(): Promise<PgTsyRuntimeSnapshot>
  abstract reloadStrategies(): Promise<PgTsyControlAck>
}

export default PgTsyRuntimeService
