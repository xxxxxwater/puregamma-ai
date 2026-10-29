import http, { type IncomingHttpHeaders, type IncomingMessage, type ServerResponse } from 'node:http'
import net from 'node:net'
import type { Duplex } from 'node:stream'
import type { BrokerConfig } from './config.ts'
import { ApiUnavailable, Authenticator, type Identity } from './identity.ts'
import { CapacityError, HostManager, QuotaError, type Host } from './hosts.ts'

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
  let pathname = new URL(mark < 0 ? raw : raw.slice(0, mark), 'http://broker.invalid').pathname
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
  close(): Promise<void>
}

type Admission = { ok: true; identity: Identity; host: Host } | { ok: false; status: number; code: string }

export function createBroker(config: BrokerConfig, deps: { fetchImpl?: typeof fetch; log?: (message: string) => void } = {}): Broker {
  const log = deps.log ?? (message => console.error(`[dsh-broker] ${message}`))
  const auth = new Authenticator(config.apiBaseUrl, config.sessionCookieName, config.authCacheMs, deps.fetchImpl)
  const hosts = new HostManager(config, log, deps.fetchImpl)

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

  async function admit(request: IncomingMessage, upgrade: boolean): Promise<Admission> {
    if (!sameSite(request, upgrade)) return { ok: false, status: 403, code: 'origin-rejected' }
    let identity: Identity | null
    try {
      identity = await auth.identify(request.headers)
    } catch (error) {
      log(`identity check failed: ${(error as Error).message}`)
      return { ok: false, status: 503, code: 'identity-unavailable' }
    }
    if (!identity) return { ok: false, status: 401, code: 'authentication-required' }
    try {
      return { ok: true, identity, host: await hosts.acquire(identity.userId, identity.credential) }
    } catch (error) {
      if (error instanceof CapacityError) return { ok: false, status: 503, code: 'capacity' }
      if (error instanceof QuotaError) return { ok: false, status: 507, code: 'storage-quota-exceeded' }
      log(`host start failed: ${(error as Error).message}`)
      return { ok: false, status: 503, code: 'host-unavailable' }
    }
  }

  function forwardHeaders(headers: IncomingHttpHeaders, host: Host): Record<string, string | string[]> {
    const out: Record<string, string | string[]> = {}
    for (const [name, value] of Object.entries(headers)) {
      if (value === undefined || DROP_REQUEST.has(name) || name.startsWith('sec-websocket') || name === 'sec-fetch-site') continue
      out[name] = value
    }
    out.host = host.authority
    out.cookie = host.cookie
    if (headers.origin !== undefined) out.origin = `http://${host.authority}`
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

  function deny(response: ServerResponse, status: number, code: string, request?: IncomingMessage): void {
    if (status === 401 && config.loginUrl && request && isNavigation(request)) {
      response.writeHead(401, { ...securityHeaders, 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' })
      response.end(`<!doctype html><meta charset="utf-8"><title>Sign in</title><p>Sign in to PureGamma to open your Harness sessions. <a href="${escapeHtml(config.loginUrl)}">Sign in</a></p>`)
      return
    }
    response.writeHead(status, { ...securityHeaders, 'content-type': 'application/json', 'cache-control': 'no-store' })
    response.end(JSON.stringify({ error: code }))
  }

  /** Root-relative redirects from a Host stay under the mount prefix. */
  function publicLocation(location: string): string {
    return config.basePath && location.startsWith('/') && !location.startsWith('//') ? `${config.basePath}${location}` : location
  }

  const server = http.createServer((request, response) => {
    if (request.url === '/__broker/healthz') return deny(response, 200, 'ok')
    const route = routeRequest(request.url, config.basePath)
    if (route.kind === 'not-found') return deny(response, 404, 'not-found')
    if (route.kind === 'redirect') {
      response.writeHead(308, { ...securityHeaders, location: route.location, 'cache-control': 'no-store' })
      return void response.end()
    }
    void admit(request, false).then(admission => {
      if (!admission.ok) return deny(response, admission.status, admission.code, request)
      const { host } = admission
      host.lastActive = Date.now()
      const upstream = http.request({
        host: '127.0.0.1', port: host.port, method: request.method, path: route.path,
        headers: forwardHeaders(request.headers, host),
      }, reply => {
        const headers: Record<string, string | string[]> = {}
        for (const [name, value] of Object.entries(reply.headers)) {
          if (value !== undefined && !DROP_RESPONSE.has(name)) headers[name] = value
        }
        if (typeof headers.location === 'string') headers.location = publicLocation(headers.location)
        Object.assign(headers, securityHeaders)
        response.writeHead(reply.statusCode ?? 502, headers)
        reply.pipe(response)
      })
      upstream.on('error', () => { if (!response.headersSent) deny(response, 502, 'host-unreachable'); else response.destroy() })
      request.pipe(upstream)
    })
  })

  server.on('upgrade', (request: IncomingMessage, socket: Duplex, head: Buffer) => {
    const fail = (status: number, code: string) => {
      socket.end(`HTTP/1.1 ${status} ${http.STATUS_CODES[status]}\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n${JSON.stringify({ error: code })}`)
    }
    socket.on('error', () => socket.destroy())
    const route = routeRequest(request.url, config.basePath)
    if (route.kind !== 'host') return fail(404, 'not-found')
    void admit(request, true).then(admission => {
      if (!admission.ok) return fail(admission.status, admission.code)
      const { host } = admission
      const upstream = net.connect(host.port, '127.0.0.1')
      host.openSockets += 1
      let closed = false
      const done = () => {
        if (closed) return
        closed = true
        host.openSockets -= 1
        host.lastActive = Date.now()
        socket.destroy()
        upstream.destroy()
      }
      // http.Server sockets are half-open: a peer FIN alone never fires
      // `close`, so either side ending tears the whole tunnel down.
      for (const side of [upstream, socket]) {
        side.on('error', done)
        side.on('end', done)
        side.on('close', done)
      }
      upstream.on('connect', () => {
        const headers = forwardHeaders(request.headers, host)
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
    })
  })

  return {
    server,
    hosts,
    async close() {
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
