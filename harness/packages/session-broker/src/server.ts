import http, { type IncomingHttpHeaders, type IncomingMessage, type ServerResponse } from 'node:http'
import net from 'node:net'
import type { Duplex } from 'node:stream'
import type { BrokerConfig } from './config.ts'
import { ApiUnavailable, Authenticator, type Identity } from './identity.ts'
import { CapacityError, HostManager, type Host } from './hosts.ts'

/** Hop-by-hop and identity headers that never cross the broker. */
const DROP_REQUEST = new Set([
  'host', 'cookie', 'authorization', 'origin', 'referer', 'connection', 'keep-alive', 'proxy-authorization',
  'proxy-connection', 'te', 'trailer', 'transfer-encoding', 'upgrade', 'forwarded', 'x-forwarded-for',
  'x-forwarded-host', 'x-forwarded-proto', 'x-real-ip',
])
const DROP_RESPONSE = new Set(['set-cookie', 'connection', 'keep-alive', 'transfer-encoding', 'trailer', 'upgrade'])

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
  function sameSite(headers: IncomingHttpHeaders, upgrade: boolean): boolean {
    if (headers['sec-fetch-site'] === 'cross-site') return false
    const origin = headers.origin
    if (origin === undefined) return !upgrade
    return origin === config.publicOrigin
  }

  async function admit(request: IncomingMessage, upgrade: boolean): Promise<Admission> {
    if (!sameSite(request.headers, upgrade)) return { ok: false, status: 403, code: 'origin-rejected' }
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
    out.host = `127.0.0.1:${host.port}`
    out.cookie = host.cookie
    if (headers.origin !== undefined) out.origin = `http://127.0.0.1:${host.port}`
    return out
  }

  /** The launch token is the broker's to use; a browser-supplied one is never forwarded. */
  function targetPath(url: string | undefined): string {
    const parsed = new URL(url ?? '/', 'http://broker.invalid')
    parsed.searchParams.delete('token')
    return `${parsed.pathname}${parsed.search}`
  }

  function deny(response: ServerResponse, status: number, code: string): void {
    response.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' })
    response.end(JSON.stringify({ error: code }))
  }

  const server = http.createServer((request, response) => {
    if (request.url === '/__broker/healthz') return deny(response, 200, 'ok')
    void admit(request, false).then(admission => {
      if (!admission.ok) return deny(response, admission.status, admission.code)
      const { host } = admission
      host.lastActive = Date.now()
      const upstream = http.request({
        host: '127.0.0.1', port: host.port, method: request.method, path: targetPath(request.url),
        headers: forwardHeaders(request.headers, host),
      }, reply => {
        const headers: Record<string, string | string[]> = {}
        for (const [name, value] of Object.entries(reply.headers)) {
          if (value !== undefined && !DROP_RESPONSE.has(name)) headers[name] = value
        }
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
        const lines = [`${request.method} ${targetPath(request.url)} HTTP/1.1`]
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
