import { createHash, createHmac, randomBytes } from 'node:crypto'
import { appendFileSync } from 'node:fs'
import type { IncomingHttpHeaders } from 'node:http'

/**
 * Structured audit trail of the broker, one JSON object per line.
 *
 * Recorded: a keyed hash of the user id (never the id, email, cookie or any
 * token), the DSH Session id and RPC namespace ("plugin") when the request
 * names them, a provider id when RPC arguments carry one, the trace id, the
 * action, the result and the duration. Never recorded: request or response
 * bodies (prompts, tool output), query strings, headers.
 */
export interface AuditEvent {
  ts: string
  event: 'http' | 'ws' | 'host' | 'revoke' | 'limit'
  action: string
  user: string | null
  session: string | null
  plugin: string | null
  provider: string | null
  trace: string
  result: string
  status: number | null
  ms: number | null
}

export type AuditSink = (line: string) => void

export function auditSink(target: string): AuditSink | undefined {
  if (!target || target === 'off') return undefined
  if (target === 'stdout') return line => process.stdout.write(`${line}\n`)
  return line => appendFileSync(target, `${line}\n`, { mode: 0o600 })
}

export class AuditLog {
  private readonly key: Buffer

  constructor(secret: string, private readonly sink: AuditSink | undefined) {
    // A keyed hash: user ids are guessable (UUIDs from the API), a plain hash
    // of one could be confirmed by anyone holding the log.
    this.key = createHash('sha256').update(`puregamma-dsh-audit\0${secret}`).digest()
  }

  get enabled(): boolean { return this.sink !== undefined }

  user(userId: string | null | undefined): string | null {
    return userId ? createHmac('sha256', this.key).update(userId).digest('hex').slice(0, 24) : null
  }

  write(event: Omit<AuditEvent, 'ts' | 'user' | 'session' | 'plugin' | 'provider' | 'status' | 'ms'> & Partial<AuditEvent> & { userId?: string | null }): void {
    if (!this.sink) return
    const { userId, ...rest } = event
    const line: AuditEvent = {
      ts: new Date().toISOString(),
      user: rest.user ?? this.user(userId),
      session: null,
      plugin: null,
      provider: null,
      status: null,
      ms: null,
      ...rest,
    }
    try { this.sink(JSON.stringify(line)) } catch {}
  }
}

const TRACEPARENT = /^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/
const REQUEST_ID = /^[A-Za-z0-9._:-]{1,128}$/

export interface Trace {
  /** The id written to the audit log (the W3C trace id, or the request id). */
  id: string
  /** Headers forwarded to the Host and FastAPI. */
  headers: { traceparent: string; 'x-request-id': string }
}

/**
 * Accept a valid W3C `traceparent` or `X-Request-Id`, otherwise mint one.
 * A new span id is used for the hop to the Host and FastAPI.
 */
export function traceOf(headers: IncomingHttpHeaders): Trace {
  const parent = typeof headers.traceparent === 'string' ? TRACEPARENT.exec(headers.traceparent.trim().toLowerCase()) : null
  const requestId = typeof headers['x-request-id'] === 'string' && REQUEST_ID.test(headers['x-request-id']) ? headers['x-request-id'] : undefined
  const traceId = parent && !/^0+$/.test(parent[1]) ? parent[1] : randomBytes(16).toString('hex')
  const flags = parent?.[3] ?? '01'
  return {
    id: parent ? traceId : requestId ?? traceId,
    headers: { traceparent: `00-${traceId}-${randomBytes(8).toString('hex')}-${flags}`, 'x-request-id': requestId ?? traceId },
  }
}

/** `/api/<namespace>/<method>` → RPC namespace and method. */
export function rpcOf(pathname: string): { plugin: string; method: string } | undefined {
  const match = /^\/api\/([A-Za-z][\w.-]{0,63})\/([A-Za-z][\w.-]{0,63})$/.exec(pathname)
  return match ? { plugin: match[1], method: match[2] } : undefined
}

export function actionOf(method: string | undefined, pathname: string): string {
  const rpc = rpcOf(pathname)
  if (rpc) return `rpc:${rpc.plugin}/${rpc.method}`
  if (pathname === '/api/remote.mux') return 'ws:remote.mux'
  if (pathname.startsWith('/plugins/') || pathname.startsWith('/assets/') || /\.(js|css|svg|png|woff2?|webmanifest|map)$/.test(pathname)) return 'asset'
  if (pathname === '/' && (method === 'GET' || method === 'HEAD')) return 'page'
  return `http:${method ?? 'GET'}`
}

const SESSION_ID = /^[A-Za-z0-9][\w.:-]{0,127}$/
const PROVIDER_ID = /^[A-Za-z0-9][\w.:/-]{0,63}$/

/**
 * Pull only identifiers out of a small JSON RPC body: the first `sessionId`
 * and `provider`/`providerId` strings within a few levels. Nothing else from
 * the body is kept.
 */
export function identifiersOf(body: string): { session: string | null; provider: string | null } {
  let parsed: unknown
  try { parsed = JSON.parse(body) } catch { return { session: null, provider: null } }
  let session: string | null = null
  let provider: string | null = null
  const walk = (value: unknown, depth: number) => {
    if (depth > 6 || value === null || typeof value !== 'object' || (session && provider)) return
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (typeof item === 'string') {
        if (!session && key === 'sessionId' && SESSION_ID.test(item)) session = item
        else if (!provider && (key === 'provider' || key === 'providerId') && PROVIDER_ID.test(item)) provider = item
      } else {
        walk(item, depth + 1)
      }
    }
  }
  walk(parsed, 0)
  return { session, provider }
}
