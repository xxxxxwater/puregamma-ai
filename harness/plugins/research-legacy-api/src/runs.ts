import type { Context } from '@deepseek-ai/cordis'
import { createBearerSource, type BearerSource, type BearerSourceConfig } from '@puregamma/dsh-legacy-auth'
import {
  ResearchRunsService,
  type ResearchJson,
  type ResearchRunEvent,
  type ResearchRunListRequest,
  type ResearchRunsDocument,
} from '@puregamma/dsh-research'

/**
 * Compatibility transport for the user's deep-research runs:
 * `GET /api/research/runs[/{id}[/artifacts|/evidence|/events]]`.
 *
 * Read-only on purpose. Create, cancel and retry spend or refund credits and
 * remain explicit actions of their own surface; nothing here can trigger them.
 */
export interface ResearchRunsClientOptions extends BearerSourceConfig {
  baseUrl: string
  requestTimeoutMs?: number
  /** Override for tests; defaults to the shared per-user/env bearer source. */
  bearer?: BearerSource
}

const SOURCE = 'compatibility:research-runs-api'
const RUN_ID = /^(?!\.+$)[A-Za-z0-9._:-]{1,160}$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toJson(value: unknown, path = '$'): ResearchJson {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`research runs payload contains non-finite number at ${path}`)
    return value
  }
  if (Array.isArray(value)) return value.map((item, index) => toJson(item, `${path}[${index}]`))
  if (isRecord(value)) {
    const output: Record<string, ResearchJson> = {}
    for (const [key, item] of Object.entries(value)) output[key] = toJson(item, `${path}.${key}`)
    return output
  }
  throw new Error(`research runs payload contains non-JSON value at ${path}`)
}

function toRecord(value: unknown): Record<string, ResearchJson> {
  if (!isRecord(value)) throw new Error('research runs compatibility API returned a non-object payload')
  return toJson(value) as Record<string, ResearchJson>
}

export function researchRunId(value: string): string {
  const normalized = typeof value === 'string' ? value.trim() : ''
  if (!RUN_ID.test(normalized)) throw new Error('research run id has an invalid format')
  return normalized
}

function boundedInteger(value: number | undefined, fallback: number, min: number, max: number, label: string): number {
  if (value === undefined) return fallback
  if (!Number.isInteger(value) || value < min || value > max) throw new Error(`${label} must be an integer between ${min} and ${max}`)
  return value
}

/** Split an SSE byte stream into `{ event, data }` frames; malformed data frames are skipped. */
export async function* parseServerSentEvents(chunks: AsyncIterable<Uint8Array>): AsyncIterable<ResearchRunEvent> {
  const decoder = new TextDecoder()
  let buffer = ''
  const flush = function* (block: string): Iterable<ResearchRunEvent> {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith(':')) continue
      const colon = line.indexOf(':')
      const field = colon === -1 ? line : line.slice(0, colon)
      const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '')
      if (field === 'event') event = value
      else if (field === 'data') data.push(value)
    }
    if (data.length === 0) return
    try {
      const parsed = JSON.parse(data.join('\n')) as unknown
      if (isRecord(parsed)) yield { event, data: toJson(parsed) as Record<string, ResearchJson> }
    } catch {
      // A frame that is not a JSON object carries nothing we can project.
    }
  }
  for await (const chunk of chunks) {
    buffer += decoder.decode(chunk, { stream: true })
    let boundary = /\r?\n\r?\n/.exec(buffer)
    while (boundary !== null) {
      const block = buffer.slice(0, boundary.index)
      buffer = buffer.slice(boundary.index + boundary[0].length)
      yield* flush(block)
      boundary = /\r?\n\r?\n/.exec(buffer)
    }
  }
  buffer += decoder.decode()
  if (buffer.trim()) yield* flush(buffer)
}

export interface ResearchRunsClient {
  listRuns(request?: ResearchRunListRequest): Promise<ResearchRunsDocument>
  run(runId: string): Promise<ResearchRunsDocument>
  artifacts(runId: string): Promise<ResearchRunsDocument>
  evidence(runId: string): Promise<ResearchRunsDocument>
  events(runId: string, signal: AbortSignal): AsyncIterable<ResearchRunEvent>
}

export function createResearchRunsClient(options: ResearchRunsClientOptions): ResearchRunsClient {
  const baseUrl = options.baseUrl.replace(/\/+$/, '')
  const bearer = options.bearer ?? createBearerSource(options)
  const timeoutMs = options.requestTimeoutMs ?? 10000
  const token = (): string => {
    const value = bearer()
    if (!value) throw new Error(`PureGamma Harness research runs provider requires bearer token in ${bearer.description}`)
    return value
  }
  const document = (kind: ResearchRunsDocument['kind'], payload: Record<string, ResearchJson>): ResearchRunsDocument =>
    ({ kind, observedAt: new Date().toISOString(), source: SOURCE, payload })
  const getJson = async (path: string): Promise<Record<string, ResearchJson>> => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await fetch(new URL(`${baseUrl}${path}`), {
        signal: controller.signal,
        headers: { Accept: 'application/json', Authorization: `Bearer ${token()}` },
      })
      // Status only: a FastAPI error body may echo request details we do not forward.
      if (!response.ok) throw new Error(`research runs compatibility API returned HTTP ${response.status}`)
      return toRecord(await response.json())
    } finally {
      clearTimeout(timer)
    }
  }
  const runPath = (runId: string): string => `/api/research/runs/${encodeURIComponent(researchRunId(runId))}`
  return {
    async listRuns(request = {}) {
      const limit = boundedInteger(request.limit, 20, 1, 100, 'limit')
      const offset = boundedInteger(request.offset, 0, 0, 100000, 'offset')
      return document('runs', await getJson(`/api/research/runs?limit=${limit}&offset=${offset}`))
    },
    async run(runId) { return document('run', await getJson(runPath(runId))) },
    async artifacts(runId) { return document('artifacts', await getJson(`${runPath(runId)}/artifacts`)) },
    async evidence(runId) { return document('evidence', await getJson(`${runPath(runId)}/evidence`)) },
    async *events(runId, signal) {
      const path = `${runPath(runId)}/events`
      const controller = new AbortController()
      const abort = (): void => controller.abort()
      if (signal.aborted) return
      signal.addEventListener('abort', abort, { once: true })
      // The timeout covers the response head only; the stream itself is bounded by the server.
      const headTimer = setTimeout(abort, timeoutMs)
      try {
        let response: Response
        try {
          response = await fetch(new URL(`${baseUrl}${path}`), {
            signal: controller.signal,
            headers: { Accept: 'text/event-stream', Authorization: `Bearer ${token()}` },
          })
        } finally {
          clearTimeout(headTimer)
        }
        if (!response.ok || !response.body) throw new Error(`research run events API returned HTTP ${response.status}`)
        try {
          for await (const event of parseServerSentEvents(response.body)) {
            if (signal.aborted) return
            yield event
          }
        } catch (error) {
          if (signal.aborted) return
          throw error
        }
      } finally {
        signal.removeEventListener('abort', abort)
        controller.abort()
      }
    },
  }
}

/**
 * `ctx.pgResearchRuns` over the legacy FastAPI routes. Mounted by the research
 * compatibility provider so the same per-user bearer source serves both.
 */
export class LegacyApiResearchRunsProvider extends ResearchRunsService {
  private readonly client: ResearchRunsClient

  constructor(ctx: Context, options: ResearchRunsClientOptions) {
    super(ctx)
    this.client = createResearchRunsClient(options)
  }

  listRuns(request?: ResearchRunListRequest): Promise<ResearchRunsDocument> { return this.client.listRuns(request) }
  run(runId: string): Promise<ResearchRunsDocument> { return this.client.run(runId) }
  artifacts(runId: string): Promise<ResearchRunsDocument> { return this.client.artifacts(runId) }
  evidence(runId: string): Promise<ResearchRunsDocument> { return this.client.evidence(runId) }
  events(runId: string, signal: AbortSignal): AsyncIterable<ResearchRunEvent> { return this.client.events(runId, signal) }
}
