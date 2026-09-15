import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import PgTsyRuntimeService, {
  type PgTsyControlAck,
  type PgTsyRunMode,
  type PgTsyRuntimeSnapshot,
} from '@puregamma/dsh-pg-tsy-runtime'

export interface Config {
  baseUrl?: string
  requestTimeoutMs?: number
  allowStrategyReload?: boolean
}

export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8080'),
  requestTimeoutMs: z.number().min(100).max(60000).default(5000),
  allowStrategyReload: z.boolean().default(false),
})

interface RawHealthSnapshot {
  process_healthy?: unknown
  ready?: unknown
  mode?: unknown
  lease_healthy?: unknown
  feeds_total?: unknown
  feeds_connected?: unknown
  events_total?: unknown
  policy_decisions_total?: unknown
  open_orders?: unknown
  orders_journaled_total?: unknown
  blocking_gates?: unknown
  last_error?: unknown
}

interface RawControlAck {
  accepted?: unknown
  command?: unknown
  reason?: unknown
}

function trimSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function finiteNumber(value: unknown, field: string): number {
  const number = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(number) || number < 0) {
    throw new Error(`pg-tsy runtime returned invalid ${field}`)
  }
  return number
}

function runMode(value: unknown): PgTsyRunMode {
  switch (String(value ?? '').toLowerCase()) {
    case 'shadow': return 'shadow'
    case 'paper': return 'paper'
    case 'live': return 'live'
    default: return 'unknown'
  }
}

function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined
}

/**
 * Adapter for pg-tsy-core's intentionally small local operator HTTP surface.
 * It does not submit/cancel/flatten orders. `/admin/reload` is additionally
 * disabled by default in this provider so merely installing the plugin cannot
 * mutate the strategy set.
 */
export class PgTsyHttpRuntimeProvider extends PgTsyRuntimeService {
  static Config = Config

  private readonly baseUrl: string
  private readonly timeoutMs: number
  private readonly allowStrategyReload: boolean

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PG_TSY_RUNTIME_URL ?? 'http://127.0.0.1:8080')
    this.timeoutMs = config.requestTimeoutMs ?? 5000
    this.allowStrategyReload = config.allowStrategyReload ?? false
  }

  private async request(path: string, init: RequestInit = {}): Promise<Response> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      return await fetch(`${this.baseUrl}${path}`, { ...init, signal: controller.signal })
    } finally {
      clearTimeout(timer)
    }
  }

  private async snapshot(path: '/healthz' | '/readyz'): Promise<PgTsyRuntimeSnapshot> {
    const response = await this.request(path, { headers: { Accept: 'application/json' } })
    const raw = await response.json() as RawHealthSnapshot
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
      throw new Error(`pg-tsy ${path} returned a non-object payload`)
    }
    const blockingGates = Array.isArray(raw.blocking_gates)
      ? raw.blocking_gates.filter((value): value is string => typeof value === 'string')
      : []
    const snapshot: PgTsyRuntimeSnapshot = {
      processHealthy: raw.process_healthy === true,
      ready: raw.ready === true,
      mode: runMode(raw.mode),
      leaseHealthy: raw.lease_healthy === true,
      feedsTotal: finiteNumber(raw.feeds_total ?? 0, 'feeds_total'),
      feedsConnected: finiteNumber(raw.feeds_connected ?? 0, 'feeds_connected'),
      eventsTotal: finiteNumber(raw.events_total ?? 0, 'events_total'),
      policyDecisionsTotal: finiteNumber(raw.policy_decisions_total ?? 0, 'policy_decisions_total'),
      openOrders: finiteNumber(raw.open_orders ?? 0, 'open_orders'),
      ordersJournaledTotal: finiteNumber(raw.orders_journaled_total ?? 0, 'orders_journaled_total'),
      blockingGates,
      ...(optionalString(raw.last_error) === undefined ? {} : { lastError: optionalString(raw.last_error) }),
      observedAt: new Date().toISOString(),
      source: this.baseUrl,
    }
    // A non-2xx readiness response is expected while booting, but a health
    // endpoint that returns non-2xx while claiming healthy is contradictory.
    if (path === '/healthz' && !response.ok && snapshot.processHealthy) {
      throw new Error(`pg-tsy /healthz returned HTTP ${response.status} with process_healthy=true`)
    }
    return snapshot
  }

  async health(): Promise<PgTsyRuntimeSnapshot> {
    return this.snapshot('/healthz')
  }

  async ready(): Promise<PgTsyRuntimeSnapshot> {
    return this.snapshot('/readyz')
  }

  async reloadStrategies(): Promise<PgTsyControlAck> {
    if (!this.allowStrategyReload) {
      return {
        accepted: false,
        command: 'reload_strategies',
        reason: 'strategy reload is disabled in the PureGamma Harness provider configuration',
        observedAt: new Date().toISOString(),
      }
    }
    const response = await this.request('/admin/reload', {
      method: 'POST',
      headers: { Accept: 'application/json' },
    })
    const raw = await response.json() as RawControlAck
    return {
      accepted: response.ok && raw.accepted === true,
      command: optionalString(raw.command) ?? 'reload_strategies',
      ...(optionalString(raw.reason) === undefined ? {} : { reason: optionalString(raw.reason) }),
      observedAt: new Date().toISOString(),
    }
  }
}

export default PgTsyHttpRuntimeProvider
