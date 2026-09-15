import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import BacktestService, {
  type BacktestArtifactBinary,
  type BacktestCompileRequest,
  type BacktestDocument,
  type BacktestDocumentKind,
  type BacktestExportFormat,
  type BacktestJson,
  type BacktestRunListRequest,
  type BacktestRunRequest,
  type BacktestTerminalEvent,
} from '@puregamma/dsh-backtest'

export interface Config {
  baseUrl?: string
  authTokenEnv?: string
  requestTimeoutMs?: number
}

export const Config: z<Config> = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
  authTokenEnv: z.string().default('PUREGAMMA_LEGACY_API_TOKEN'),
  requestTimeoutMs: z.number().min(100).max(120000).default(30000),
})

function trimSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toBacktestJson(value: unknown, path = '$'): BacktestJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`backtest compatibility payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toBacktestJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const output: Record<string, BacktestJson> = {}
    for (const [key, item] of Object.entries(value)) output[key] = toBacktestJson(item, `${path}.${key}`)
    return output
  }
  throw new Error(`backtest compatibility payload contains non-JSON value at ${path}`)
}

function toBacktestRecord(value: unknown): Record<string, BacktestJson> {
  if (!isRecord(value)) throw new Error('backtest compatibility API returned a non-object payload')
  return toBacktestJson(value) as Record<string, BacktestJson>
}

function normalizeIdentifier(value: string, label: string, max = 128): string {
  const normalized = value.trim()
  if (normalized.length < 1 || normalized.length > max || !/^[A-Za-z0-9._:-]+$/.test(normalized)) {
    throw new Error(`${label} has an invalid format`)
  }
  return normalized
}

function normalizeWindowDays(value: number): number {
  if (!Number.isInteger(value) || value < 1 || value > 30) throw new Error('windowDays must be an integer between 1 and 30')
  return value
}

function normalizeLimit(value: number): number {
  if (!Number.isInteger(value) || value < 1 || value > 50) throw new Error('limit must be an integer between 1 and 50')
  return value
}

function normalizeOffset(value: number): number {
  if (!Number.isInteger(value) || value < 0) throw new Error('offset must be a non-negative integer')
  return value
}

function contentDispositionFileName(header: string | null): string | undefined {
  if (!header) return undefined
  const match = header.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i)
  return match?.[1]?.trim()
}

function decodeSseBlock(block: string): BacktestTerminalEvent | undefined {
  let sequence: number | undefined
  let eventType = 'message'
  const data: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('id:')) {
      const parsed = Number.parseInt(line.slice(3).trim(), 10)
      if (Number.isFinite(parsed) && parsed > 0) sequence = parsed
    } else if (line.startsWith('event:')) {
      eventType = line.slice(6).trim() || 'message'
    } else if (line.startsWith('data:')) {
      data.push(line.slice(5).trimStart())
    }
  }
  if (data.length === 0) return undefined
  let parsed: Record<string, BacktestJson>
  try {
    parsed = toBacktestRecord(JSON.parse(data.join('\n')))
  } catch {
    parsed = { raw: data.join('\n') }
  }
  const line = typeof parsed.line === 'string' ? parsed.line : undefined
  const type = typeof parsed.t === 'string' ? parsed.t : eventType
  return {
    ...(sequence === undefined ? {} : { sequence }),
    type,
    ...(line === undefined ? {} : { line }),
    payload: parsed,
  }
}

/**
 * Migration provider for the existing backtest APIs.
 *
 * Every in-flight HTTP/SSE request is represented by an AbortController owned
 * by a Cordis effect. Unloading the plugin aborts them all, satisfying temporal
 * composability instead of leaving long-lived terminal streams behind.
 */
export class LegacyApiBacktestProvider extends BacktestService {
  static Config = Config

  private readonly baseUrl: string
  private readonly tokenEnv: string
  private readonly timeoutMs: number
  private readonly controllers = new Set<AbortController>()

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.baseUrl = trimSlash(config.baseUrl ?? process.env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000')
    this.tokenEnv = config.authTokenEnv ?? 'PUREGAMMA_LEGACY_API_TOKEN'
    this.timeoutMs = config.requestTimeoutMs ?? 30000

    ctx.effect(() => () => {
      for (const controller of this.controllers) controller.abort()
      this.controllers.clear()
    }, 'pgBacktest.abort-inflight')
  }

  private token(): string {
    const token = process.env[this.tokenEnv]
    if (!token) throw new Error(`PureGamma Harness backtest compatibility provider requires bearer token in ${this.tokenEnv}`)
    return token
  }

  private controller(): AbortController {
    const controller = new AbortController()
    this.controllers.add(controller)
    return controller
  }

  private release(controller: AbortController): void {
    this.controllers.delete(controller)
  }

  private url(path: string, query: Record<string, string | number | undefined> = {}): URL {
    const url = new URL(`${this.baseUrl}${path}`)
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
    return url
  }

  private async requestJson(
    method: 'GET' | 'POST',
    path: string,
    options: { query?: Record<string, string | number | undefined>; body?: unknown } = {},
  ): Promise<Record<string, BacktestJson>> {
    const controller = this.controller()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(this.url(path, options.query), {
        method,
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${this.token()}`,
          ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
      })
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 400)
        throw new Error(`backtest compatibility API returned HTTP ${response.status} for ${path}${detail ? `: ${detail}` : ''}`)
      }
      return toBacktestRecord(await response.json())
    } finally {
      clearTimeout(timer)
      this.release(controller)
    }
  }

  private document(kind: BacktestDocumentKind, payload: Record<string, BacktestJson>): BacktestDocument {
    return {
      kind,
      observedAt: new Date().toISOString(),
      source: 'compatibility:backtest-api',
      payload,
    }
  }

  async status(): Promise<BacktestDocument> {
    return this.document('status', await this.requestJson('GET', '/backtest-lab/status'))
  }

  async compile(request: BacktestCompileRequest): Promise<BacktestDocument> {
    const idea = request.idea.trim()
    if (idea.length > 2000) throw new Error('backtest idea must be at most 2000 characters')
    return this.document('spec', await this.requestJson('POST', '/backtest-lab/generate-spec', {
      body: {
        idea,
        use_memory: request.useMemory ?? true,
        locale: request.locale ?? 'en',
      },
    }))
  }

  async run(request: BacktestRunRequest): Promise<BacktestDocument> {
    const idempotencyKey = normalizeIdentifier(request.idempotencyKey, 'idempotencyKey', 120)
    return this.document('run', await this.requestJson('POST', '/backtest-lab/runs', {
      body: {
        spec: request.spec,
        window_days: normalizeWindowDays(request.windowDays ?? 30),
        idempotency_key: idempotencyKey,
        context_meta: request.contextMeta ?? {},
      },
    }))
  }

  async listRuns(request: BacktestRunListRequest = {}): Promise<BacktestDocument> {
    return this.document('runs', await this.requestJson('GET', '/backtest-lab/runs', {
      query: {
        limit: normalizeLimit(request.limit ?? 20),
        offset: normalizeOffset(request.offset ?? 0),
      },
    }))
  }

  async result(runId: string): Promise<BacktestDocument> {
    const id = normalizeIdentifier(runId, 'runId')
    return this.document('run', await this.requestJson('GET', `/backtest-lab/runs/${encodeURIComponent(id)}`))
  }

  async cancel(runId: string): Promise<BacktestDocument> {
    const id = normalizeIdentifier(runId, 'runId')
    return this.document('run', await this.requestJson('POST', `/backtest/${encodeURIComponent(id)}/cancel`))
  }

  async exportRun(runId: string, format: BacktestExportFormat = 'json'): Promise<BacktestDocument> {
    const id = normalizeIdentifier(runId, 'runId')
    return this.document('artifact', await this.requestJson('POST', `/backtest-lab/runs/${encodeURIComponent(id)}/export`, {
      query: { format },
    }))
  }

  async saveAsStrategy(runId: string): Promise<BacktestDocument> {
    const id = normalizeIdentifier(runId, 'runId')
    return this.document('strategy', await this.requestJson('POST', `/backtest/${encodeURIComponent(id)}/save-as-strategy`))
  }

  async refreshData(): Promise<BacktestDocument> {
    return this.document('data-status', await this.requestJson('POST', '/backtest-lab/data/refresh'))
  }

  async *terminalEvents(runId: string, afterSequence = 0): AsyncIterable<BacktestTerminalEvent> {
    const id = normalizeIdentifier(runId, 'runId')
    if (!Number.isInteger(afterSequence) || afterSequence < 0) throw new Error('afterSequence must be a non-negative integer')
    const controller = this.controller()
    try {
      const response = await fetch(this.url(`/backtest-lab/runs/${encodeURIComponent(id)}/stream`), {
        signal: controller.signal,
        headers: {
          Accept: 'text/event-stream',
          Authorization: `Bearer ${this.token()}`,
          ...(afterSequence > 0 ? { 'Last-Event-ID': String(afterSequence) } : {}),
        },
      })
      if (!response.ok || !response.body) {
        throw new Error(`backtest terminal stream returned HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      try {
        while (true) {
          const chunk = await reader.read()
          if (chunk.done) break
          buffer += decoder.decode(chunk.value, { stream: true })
          while (true) {
            const match = buffer.match(/\r?\n\r?\n/)
            if (!match || match.index === undefined) break
            const block = buffer.slice(0, match.index)
            buffer = buffer.slice(match.index + match[0].length)
            const event = decodeSseBlock(block)
            if (event) yield event
          }
        }
        buffer += decoder.decode()
        const event = decodeSseBlock(buffer)
        if (event) yield event
      } finally {
        await reader.cancel().catch(() => undefined)
      }
    } finally {
      controller.abort()
      this.release(controller)
    }
  }

  async artifact(artifactId: string): Promise<BacktestArtifactBinary> {
    const id = normalizeIdentifier(artifactId, 'artifactId')
    const controller = this.controller()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(this.url(`/backtest-lab/artifacts/${encodeURIComponent(id)}`), {
        signal: controller.signal,
        headers: {
          Accept: 'application/octet-stream, application/json, text/csv',
          Authorization: `Bearer ${this.token()}`,
        },
      })
      if (!response.ok) throw new Error(`backtest artifact API returned HTTP ${response.status}`)
      return {
        contentType: response.headers.get('content-type') ?? 'application/octet-stream',
        ...(contentDispositionFileName(response.headers.get('content-disposition')) === undefined
          ? {}
          : { fileName: contentDispositionFileName(response.headers.get('content-disposition')) }),
        bytes: new Uint8Array(await response.arrayBuffer()),
      }
    } finally {
      clearTimeout(timer)
      this.release(controller)
    }
  }
}

export default LegacyApiBacktestProvider
