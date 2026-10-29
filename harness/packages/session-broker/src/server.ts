import { createHash, timingSafeEqual } from 'node:crypto'
import http, { type IncomingHttpHeaders, type IncomingMessage, type ServerResponse } from 'node:http'
import net from 'node:net'
import type { Duplex } from 'node:stream'
import { AuditLog, actionOf, auditSink, identifiersOf, rpcOf, traceOf, type Trace } from './audit.ts'
import type { BrokerConfig } from './config.ts'
import { Authenticator, type Identity, type UserCredential } from './identity.ts'
import { CapacityError, HostManager, QuotaError, type Host } from './hosts.ts'
import { Concurrency, KeyedBuckets, RateLimited } from './limits.ts'

/** Hop-by-hop and identity headers that never cross the broker. */
const DROP_REQUEST = new Set([
  'host', 'cookie', 'authorization', 'origin', 'referer', 'connection', 'keep-alive', 'proxy-authorization',
  'proxy-connection', 'te', 'trailer', 'transfer-encoding', 'upgrade', 'forwarded', 'x-forwarded-for',
  'x-forwarded-host', 'x-forwarded-proto', 'x-real-ip',
])
const DROP_RESPONSE = new Set(['set-cookie', 'connection', 'keep-alive', 'transfer-encoding', 'trailer', 'upgrade'])

/** Where a request goes once the mount prefix is checked. */
export type Route = { kind: 'host'; path: string } | { kind: 'redirect'; location: string } | { kind: 'not-found' }

/**
 * Map a public request URL onto the Host. Outside the mount prefix nothing
 * is routed (and no identity check or Host start happens); the bare prefix
 * redirects to its trailing-slash form so DSH's relative URLs resolve under
 * it. A browser-supplied launch `token` is never forwarded.
 */
export function routeRequest(url: string | undefined, basePath: string): Route {
  const raw = url ?? '/'
  const mark = raw.indexOf('?')
  const search = withoutLaunchToken(mark < 0 ? '' : raw.slice(mark))
  let pathname: string
  try {
    pathname = new URL(mark < 0 ? raw : raw.slice(0, mark), 'http://broker.invalid').pathname
  } catch {
    return { kind: 'not-found' }
  }
  if (basePath) {
    if (pathname === basePath) return { kind: 'redirect', location: `${basePath}/${search}` }
    if (!pathname.startsWith(`${basePath}/`)) return { kind: 'not-found' }
    pathname = pathname.slice(basePath.length)
  }
  return { kind: 'host', path: `${pathname}${search}` }
}

/**
 * Drop every `token` parameter from a raw query string and keep the rest
 * byte-for-byte. DSH's combo bundle URLs (`plugins/??a/client.js,b/client.js&rev=…`)
 * do not survive a URLSearchParams round trip.
 */
export function withoutLaunchToken(search: string): string {
  if (!search) return ''
  const kept = search.slice(1).split('&').filter(part => {
    const name = part.split('=', 1)[0]
    let decoded = name
    try { decoded = decodeURIComponent(name.replace(/\+/g, ' ')) } catch {}
    return decoded !== 'token'
  })
  return kept.length ? `?${kept.join('&')}` : ''
}

/**
 * A top-level document navigation (link click, typed URL) carries no Origin
 * and may be cross-site; it is a read of the app shell, never an RPC, so it is
 * admitted like any same-site request. Everything else that is cross-site is
 * refused, and WebSocket upgrades always need the public Origin.
 */
export function isNavigation(request: Pick<IncomingMessage, 'method' | 'headers'>): boolean {
  return (request.method === 'GET' || request.method === 'HEAD')
    && request.headers['sec-fetch-mode'] === 'navigate'
    && request.headers['sec-fetch-dest'] === 'document'
    && request.headers.origin === undefined
}

export interface Broker {
  server: http.Server
  hosts: HostManager
  /** Open WebSocket tunnels per user (counts only). */
  sockets(): number
  /** Re-check every open tunnel's credential now (also runs on a timer). */
  revalidateSockets(): Promise<number>
  close(): Promise<void>
}

type Admission =
  | { ok: true; identity: Identity; host: Host; release: () => void }
  | { ok: false; status: number; code: string; retryAfterSec?: number; userId?: string }

interface Tunnel { userId: string; credential: UserCredential; close(reason: string): void }

/** Bodies the audit log may inspect for identifiers (RPC JSON only). */
const AUDIT_BODY_MAX = 64 * 1024
const REVOKE_PATH = '/__broker/revoke'

export function createBroker(
  config: BrokerConfig,
  deps: { fetchImpl?: typeof fetch; log?: (message: string) => void; auditSink?: (line: string) => void } = {},
): Broker {
  const log = deps.log ?? (message => console.error(`[dsh-broker] ${message}`))
  const audit = new AuditLog(config.brokerSecret, deps.auditSink ?? auditSink(config.audit))
  const auth = new Authenticator(config.apiBaseUrl, config.sessionCookieName, config.authCacheMs, deps.fetchImpl)
  const hosts = new HostManager(config, log, deps.fetchImpl, undefined, event => audit.write({
    event: 'host', action: `host:${event.action}`, userId: event.userId, trace: '-',
    result: event.reason ? `${event.result}:${event.reason}` : event.result, ms: event.ms ?? null,
  }))
  const limits = config.limits
  const userRates = new KeyedBuckets(limits.userBurst, limits.userRatePerSec)
  const lookupRates = new KeyedBuckets(limits.ipLookupBurst, limits.ipLookupRatePerSec)
  const inflight = new Concurrency(limits.userMaxInflight)
  const socketSlots = new Concurrency(limits.userMaxSockets)
  const tunnels = new Map<string, Set<Tunnel>>()

  /**
   * DSH's own Host/Origin fence only sees the rewritten loopback request, so
   * the browser-facing fence is enforced here: a present Origin must be the
   * public origin, cross-site fetch metadata is refused, and WebSocket
   * upgrades must carry the public Origin.
   */
  function sameSite(request: IncomingMessage, upgrade: boolean): boolean {
    const headers = request.headers
    if (!upgrade && isNavigation(request)) return true
    if (headers['sec-fetch-site'] === 'cross-site') return false
    const origin = headers.origin
    if (origin === undefined) return !upgrade
    return origin === config.publicOrigin
  }

  /** The edge-provided client address when configured (Caddy's X-Real-IP), else the socket peer. */
  function clientAddress(request: IncomingMessage): string {
    const header = config.clientIpHeader ? request.headers[config.clientIpHeader] : undefined
    const value = typeof header === 'string' ? header.trim().slice(0, 64) : ''
    return value || request.socket.remoteAddress || 'unknown'
  }

  /**
   * Order: Origin fence → identity (FastAPI lookups rate limited per client
   * address) → per-user rate → per-user concurrency → Host (global start
   * rate, capacity, disk quota). Every refusal names its reason.
   */
  async function admit(request: IncomingMessage, upgrade: boolean, trace: Trace): Promise<Admission> {
    if (!sameSite(request, upgrade)) return { ok: false, status: 403, code: 'origin-rejected' }
    let identity: Identity | null
    try {
      const address = clientAddress(request)
      identity = await auth.identify(request.headers, {
        trace: trace.headers,
        gate: () => {
          const lookup = lookupRates.take(address)
          if (!lookup.ok) throw new RateLimited('lookup-rate', lookup.retryAfterSec)
        },
      })
    } catch (error) {
      if (error instanceof RateLimited) return { ok: false, status: 429, code: error.code, retryAfterSec: error.retryAfterSec }
      log(`identity check failed: ${(error as Error).message}`)
      return { ok: false, status: 503, code: 'identity-unavailable' }
    }
    if (!identity) return { ok: false, status: 401, code: 'authentication-required' }
    const userId = identity.userId
    const rate = userRates.take(userId)
    if (!rate.ok) return { ok: false, status: 429, code: 'rate-limited', retryAfterSec: rate.retryAfterSec, userId }
    const release = (upgrade ? socketSlots : inflight).acquire(userId)
    if (!release) return { ok: false, status: 429, code: upgrade ? 'too-many-sockets' : 'too-many-requests', retryAfterSec: 1, userId }
    try {
      return { ok: true, identity, host: await hosts.acquire(userId, identity.credential, trace.headers), release }
    } catch (error) {
      release()
      if (error instanceof RateLimited) return { ok: false, status: 429, code: error.code, retryAfterSec: error.retryAfterSec, userId }
      if (error instanceof CapacityError) return { ok: false, status: 503, code: 'capacity', retryAfterSec: 30, userId }
      if (error instanceof QuotaError) return { ok: false, status: 507, code: 'storage-quota-exceeded', userId }
      log(`host start failed: ${(error as Error).message}`)
      return { ok: false, status: 503, code: 'host-unavailable', userId }
    }
  }

  function forwardHeaders(headers: IncomingHttpHeaders, host: Host, trace: Trace): Record<string, string | string[]> {
    const out: Record<string, string | string[]> = {}
    for (const [name, value] of Object.entries(headers)) {
      if (value === undefined || DROP_REQUEST.has(name) || name.startsWith('sec-websocket') || name === 'sec-fetch-site') continue
      if (name === 'traceparent' || name === 'tracestate' || name === 'x-request-id') continue
      out[name] = value
    }
    out.host = host.authority
    out.cookie = host.cookie
    if (headers.origin !== undefined) out.origin = `http://${host.authority}`
    Object.assign(out, trace.headers)
    return out
  }

  /** Headers every broker response carries, whether it came from a Host or not. */
  const securityHeaders: Record<string, string> = {
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer',
    'x-frame-options': 'DENY',
    'cross-origin-opener-policy': 'same-origin',
    ...(config.contentSecurityPolicy ? { 'content-security-policy': config.contentSecurityPolicy } : {}),
  }

  function deny(response: ServerResponse, status: number, code: string, request?: IncomingMessage, extra: Record<string, string> = {}): void {
    if (status === 401 && config.loginUrl && request && isNavigation(request)) {
      response.writeHead(401, { ...securityHeaders, ...extra, 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' })
      response.end(`<!doctype html><meta charset="utf-8"><title>Sign in</title><p>Sign in to PureGamma to open your Harness sessions. <a href="${escapeHtml(config.loginUrl)}">Sign in</a></p>`)
      return
    }
    response.writeHead(status, { ...securityHeaders, ...extra, 'content-type': 'application/json', 'cache-control': 'no-store' })
    response.end(JSON.stringify({ error: code }))
  }

  const refusalHeaders = (admission: { retryAfterSec?: number }, trace: Trace) => ({
    'x-request-id': trace.headers['x-request-id'],
    ...(admission.retryAfterSec ? { 'retry-after': String(admission.retryAfterSec) } : {}),
  })

  /** Root-relative redirects from a Host stay under the mount prefix. */
  function publicLocation(location: string): string {
    return config.basePath && location.startsWith('/') && !location.startsWith('//') ? `${config.basePath}${location}` : location
  }

  function closeTunnels(userId: string, reason: string): number {
    const set = tunnels.get(userId)
    if (!set) return 0
    const count = set.size
    for (const tunnel of [...set]) tunnel.close(reason)
    return count
  }

  const secretDigest = createHash('sha256').update(config.brokerSecret).digest()
  function secretMatches(value: string | string[] | undefined): boolean {
    if (typeof value !== 'string' || config.brokerSecret.length < 32) return false
    return timingSafeEqual(createHash('sha256').update(value).digest(), secretDigest)
  }

  /**
   * Logout notification from FastAPI: forget the user's cached identities,
   * close their WebSockets and stop their Host (its token file goes with it).
   * Needs the broker secret; the edge does not route /__broker/* at all.
   */
  function revoke(request: IncomingMessage, response: ServerResponse, trace: Trace): void {
    const started = Date.now()
    if (request.method !== 'POST') return deny(response, 405, 'method-not-allowed')
    if (!secretMatches(request.headers['x-puregamma-broker-secret'])) {
      audit.write({ event: 'revoke', action: 'revoke', trace: trace.id, result: 'forbidden', status: 403 })
      request.resume()
      return deny(response, 403, 'forbidden')
    }
    let body = ''
    request.setEncoding('utf8')
    request.on('data', chunk => {
      body += chunk
      if (body.length > 1024) request.destroy()
    })
    request.on('end', () => {
      let userId: unknown
      try { userId = (JSON.parse(body) as { user_id?: unknown }).user_id } catch {}
      if (typeof userId !== 'string' || !userId || userId.length > 64) return deny(response, 400, 'user-id-required')
      const forgotten = auth.forgetUser(userId)
      const closed = closeTunnels(userId, 'revoked')
      void hosts.stop(userId, 'revoked').catch(error => log(`revoke stop failed: ${(error as Error).message}`)).then(() => {
        audit.write({ event: 'revoke', action: 'revoke', userId, trace: trace.id, result: `ok:${forgotten}c/${closed}s`, status: 204, ms: Date.now() - started })
        response.writeHead(204, { 'cache-control': 'no-store' })
        response.end()
      })
    })
  }

  const server = http.createServer((request, response) => {
    const started = Date.now()
    if (request.url === '/__broker/healthz') return deny(response, 200, 'ok')
    const trace = traceOf(request.headers)
    if (request.url?.split('?')[0] === REVOKE_PATH) return revoke(request, response, trace)
    const route = routeRequest(request.url, config.basePath)
    if (route.kind === 'not-found') return deny(response, 404, 'not-found')
    if (route.kind === 'redirect') {
      response.writeHead(308, { ...securityHeaders, location: route.location, 'cache-control': 'no-store' })
      return void response.end()
    }
    const pathname = route.path.split('?')[0]
    const action = actionOf(request.method, pathname)
    const rpc = rpcOf(pathname)
    void admit(request, false, trace).then(admission => {
      if (!admission.ok) {
        audit.write({ event: admission.status === 429 ? 'limit' : 'http', action, userId: admission.userId, plugin: rpc?.plugin ?? null, trace: trace.id, result: admission.code, status: admission.status, ms: Date.now() - started })
        return deny(response, admission.status, admission.code, request, refusalHeaders(admission, trace))
      }
      const { host, identity, release } = admission
      if (response.destroyed) return release()
      host.lastActive = Date.now()
      // Small RPC JSON bodies are scanned for identifiers only (Session id,
      // provider id) when the request ends; the bytes are never logged.
      const inspect = rpc !== undefined && audit.enabled
      let requestBody = ''
      let responseBody = ''
      if (inspect) request.on('data', chunk => { if (requestBody.length < AUDIT_BODY_MAX) requestBody += String(chunk).slice(0, AUDIT_BODY_MAX - requestBody.length) })
      let status: number | null = null
      const finish = (result: string) => {
        release()
        if (action === 'asset' && !config.auditAssets && result === 'ok') return
        const ids = inspect ? identifiersOf(requestBody) : { session: null, provider: null }
        const fromReply = inspect && !ids.session ? identifiersOf(responseBody) : { session: null, provider: null }
        audit.write({
          event: 'http', action, userId: identity.userId, plugin: rpc?.plugin ?? null,
          session: ids.session ?? fromReply.session, provider: ids.provider ?? fromReply.provider,
          trace: trace.id, result, status, ms: Date.now() - started,
        })
      }
      response.once('close', () => finish(response.writableFinished ? 'ok' : 'aborted'))
      const upstream = http.request({
        host: '127.0.0.1', port: host.port, method: request.method, path: route.path,
        headers: forwardHeaders(request.headers, host, trace),
      }, reply => {
        const headers: Record<string, string | string[]> = {}
        for (const [name, value] of Object.entries(reply.headers)) {
          if (value !== undefined && !DROP_RESPONSE.has(name)) headers[name] = value
        }
        if (typeof headers.location === 'string') headers.location = publicLocation(headers.location)
        Object.assign(headers, securityHeaders, { 'x-request-id': trace.headers['x-request-id'] })
        status = reply.statusCode ?? 502
        if (inspect && /json/.test(String(reply.headers['content-type'] ?? ''))) {
          reply.on('data', chunk => { if (responseBody.length < AUDIT_BODY_MAX) responseBody += String(chunk).slice(0, AUDIT_BODY_MAX - responseBody.length) })
        }
        response.writeHead(status, headers)
        reply.pipe(response)
      })
      response.once('close', () => { if (!response.writableFinished) upstream.destroy() })
      upstream.on('error', () => {
        status = 502
        if (!response.headersSent) deny(response, 502, 'host-unreachable')
        else response.destroy()
      })
      request.pipe(upstream)
    }).catch(error => {
      log(`request failed: ${(error as Error).message}`)
      if (!response.headersSent) deny(response, 500, 'internal-error')
      else response.destroy()
    })
  })

  server.on('upgrade', (request: IncomingMessage, socket: Duplex, head: Buffer) => {
    const started = Date.now()
    const trace = traceOf(request.headers)
    const fail = (status: number, code: string, retryAfterSec?: number) => {
      const retry = retryAfterSec ? `Retry-After: ${retryAfterSec}\r\n` : ''
      socket.end(`HTTP/1.1 ${status} ${http.STATUS_CODES[status]}\r\nContent-Type: application/json\r\n${retry}Connection: close\r\n\r\n${JSON.stringify({ error: code })}`)
    }
    socket.on('error', () => socket.destroy())
    const route = routeRequest(request.url, config.basePath)
    if (route.kind !== 'host') return fail(404, 'not-found')
    const action = actionOf('GET', route.path.split('?')[0])
    void admit(request, true, trace).then(admission => {
      if (!admission.ok) {
        audit.write({ event: admission.status === 429 ? 'limit' : 'ws', action, userId: admission.userId, trace: trace.id, result: admission.code, status: admission.status, ms: Date.now() - started })
        return fail(admission.status, admission.code, admission.retryAfterSec)
      }
      const { host, identity, release } = admission
      if (socket.destroyed || socket.readableEnded) {
        release()
        return void socket.destroy()
      }
      const upstream = net.connect(host.port, '127.0.0.1')
      host.openSockets += 1
      let closed = false
      let reason = 'closed'
      const tunnel: Tunnel = {
        userId: identity.userId,
        credential: identity.credential,
        close: why => { reason = why; done() },
      }
      const set = tunnels.get(identity.userId) ?? new Set<Tunnel>()
      set.add(tunnel)
      tunnels.set(identity.userId, set)
      audit.write({ event: 'ws', action, userId: identity.userId, trace: trace.id, result: 'open', status: 101 })
      function done() {
        if (closed) return
        closed = true
        host.openSockets -= 1
        host.lastActive = Date.now()
        release()
        set.delete(tunnel)
        if (!set.size && tunnels.get(identity.userId) === set) tunnels.delete(identity.userId)
        socket.destroy()
        upstream.destroy()
        audit.write({ event: 'ws', action, userId: identity.userId, trace: trace.id, result: reason, status: 101, ms: Date.now() - started })
      }
      // http.Server sockets are half-open: a peer FIN alone never fires
      // `close`, so either side ending tears the whole tunnel down.
      for (const side of [upstream, socket]) {
        side.on('error', done)
        side.on('end', done)
        side.on('close', done)
      }
      upstream.on('connect', () => {
        const headers = forwardHeaders(request.headers, host, trace)
        headers.connection = 'Upgrade'
        headers.upgrade = String(request.headers.upgrade ?? 'websocket')
        for (const [name, value] of Object.entries(request.headers)) {
          if (name.startsWith('sec-websocket') && value !== undefined) headers[name] = value
        }
        const lines = [`${request.method} ${route.path} HTTP/1.1`]
        for (const [name, value] of Object.entries(headers)) {
          for (const item of Array.isArray(value) ? value : [value]) lines.push(`${name}: ${item}`)
        }
        upstream.write(`${lines.join('\r\n')}\r\n\r\n`)
        if (head.length) upstream.write(head)
        upstream.pipe(socket)
        socket.pipe(upstream)
      })
    }).catch(error => {
      log(`upgrade failed: ${(error as Error).message}`)
      socket.destroy()
    })
  })

  /**
   * A tunnel authenticated once stays open for as long as the browser keeps
   * it; re-check each tunnel's credential (through the same short cache) and
   * close those whose user logged out or whose session was replaced. An API
   * outage keeps tunnels open (logged), it does not drop every user.
   */
  async function revalidateSockets(): Promise<number> {
    let closed = 0
    for (const set of [...tunnels.values()]) {
      for (const tunnel of [...set]) {
        try {
          const identity = await auth.identifyCredential(tunnel.credential)
          if (!identity || identity.userId !== tunnel.userId) {
            tunnel.close('revalidation-failed')
            closed += 1
          }
        } catch (error) {
          log(`socket revalidation skipped: ${(error as Error).message}`)
        }
      }
    }
    return closed
  }
  const revalidator = config.socketRevalidateMs > 0 ? setInterval(() => void revalidateSockets(), config.socketRevalidateMs) : undefined
  revalidator?.unref()

  return {
    server,
    hosts,
    sockets: () => [...tunnels.values()].reduce((sum, set) => sum + set.size, 0),
    revalidateSockets,
    async close() {
      clearInterval(revalidator)
      for (const userId of [...tunnels.keys()]) closeTunnels(userId, 'shutdown')
      await hosts.close()
      const closed = new Promise<void>(resolve => server.close(() => resolve()))
      server.closeAllConnections()
      await closed
    },
  }
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, char => `&#${char.charCodeAt(0)};`)
}
