import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import PgTsyRuntimeService, {
  type PgTsyControlAck,
  type PgTsyRuntimeSnapshot,
} from '@puregamma/dsh-pg-tsy-runtime'
import { parsePgTsyHealth, type HealthPath } from './health-contract.ts'

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

function trimSlash(value: string): string { return value.replace(/\/+$/, '') }
function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/**
 * Operator-only adapter to pinned Rust pg-core. It has no order submission,
 * cancellation, flatten, mandate grant or permission-activation method.
 * Reload remains opt-in and unavailable to model tools.
 */
export class PgTsyHttpRuntimeProvider extends PgTsyRuntimeService {
  static Config = Config

  private readonly baseUrl: string
  private readonly timeoutMs: number
  private readonly allowStrategyReload: boolean
  private readonly controllers = new Set<AbortController>()

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PG_TSY_RUNTIME_URL ?? 'http://127.0.0.1:8080')
    this.timeoutMs = config.requestTimeoutMs ?? 5000
    this.allowStrategyReload = config.allowStrategyReload ?? false
    // Cordis owns in-flight HTTP effects: uninstall/hot reload aborts every fetch.
    ctx.effect(() => () => {
      for (const controller of this.controllers) controller.abort()
      this.controllers.clear()
    }, 'pgTsyRuntime.abort-inflight')
  }

  private async requestJson(path: HealthPath | '/admin/reload', method: 'GET' | 'POST' = 'GET'): Promise<{ status: number; payload: unknown }> {
    const controller = new AbortController()
    this.controllers.add(controller)
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method, signal: controller.signal, headers: { Accept: 'application/json' },
      })
      // The timeout MUST span body consumption too, not just receipt of headers.
      const payload: unknown = await response.json()
      return { status: response.status, payload }
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private async snapshot(path: HealthPath): Promise<PgTsyRuntimeSnapshot> {
    const { status, payload } = await this.requestJson(path)
    return parsePgTsyHealth(payload, path, status, this.baseUrl)
  }

  async health(): Promise<PgTsyRuntimeSnapshot> { return this.snapshot('/healthz') }
  async ready(): Promise<PgTsyRuntimeSnapshot> { return this.snapshot('/readyz') }

  async reloadStrategies(): Promise<PgTsyControlAck> {
    if (!this.allowStrategyReload) {
      return {
        accepted: false, command: 'reload_strategies',
        reason: 'strategy reload is disabled in the PureGamma Harness provider configuration',
        observedAt: new Date().toISOString(),
      }
    }
    const { status, payload } = await this.requestJson('/admin/reload', 'POST')
    if (!isRecord(payload)) throw new Error('pg-tsy reload returned an invalid acknowledgement')
    return {
      accepted: status === 202 && payload.accepted === true,
      command: optionalString(payload.command) ?? 'reload_strategies',
      ...(optionalString(payload.reason) === undefined ? {} : { reason: optionalString(payload.reason) }),
      observedAt: new Date().toISOString(),
    }
  }
}

export default PgTsyHttpRuntimeProvider
