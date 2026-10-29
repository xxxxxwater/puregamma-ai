// Shared scaffolding for broker tests: a fake FastAPI (`GET /me` + the Host
// token mint) and helpers to talk to a broker over HTTP and WebSocket.
import { randomBytes } from 'node:crypto'
import http from 'node:http'
import path from 'node:path'
import { loadConfig } from '../../packages/session-broker/src/index.ts'

export const SESSIONS = { 'sess-a': 'user-a', 'sess-b': 'user-b', 'sess-c': 'user-c', 'sess-d': 'user-d' }

export async function startFakeApi({ sessions = SESSIONS, secret } = {}) {
  const calls = []
  let mints = 0
  const server = http.createServer((req, res) => {
    calls.push({ url: req.url, headers: req.headers })
    const cookie = /pg_session=([^;]+)/.exec(req.headers.cookie ?? '')?.[1]
    const bearer = /^Bearer (.+)$/.exec(req.headers.authorization ?? '')?.[1]
    const user = sessions[cookie ?? bearer] ?? (bearer?.startsWith('host.') ? bearer.split('.')[1] : undefined)
    const send = (status, body) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)) }
    if (req.url === '/me') return user ? send(200, { user: { id: user } }) : send(401, { detail: 'no' })
    if (req.url === '/internal/dsh/host-tokens' && req.method === 'POST') {
      if (req.headers['x-puregamma-broker-secret'] !== secret) return send(403, {})
      if (!user) return send(401, {})
      mints += 1
      return send(200, { token: `host.${user}.${mints}`, user_id: user, expires_at: Math.floor(Date.now() / 1000) + 600 })
    }
    send(404, {})
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  return { server, calls, url: `http://127.0.0.1:${server.address().port}`, close: () => new Promise(resolve => server.close(resolve)) }
}

export function brokerConfig({ api, root, harness, secret, ...overrides }) {
  return {
    ...loadConfig({}),
    enabled: true,
    publicOrigin: 'https://harness.puregamma.test',
    apiBaseUrl: api.url,
    hostApiBaseUrl: api.url,
    brokerSecret: secret,
    hostsRoot: path.join(root, 'hosts'),
    dshBin: path.join(harness, 'scripts', 'fixtures', 'fake-dsh-host.mjs'),
    profileDir: harness,
    patchFiles: [],
    maxHosts: 4,
    idleMs: 60_000,
    startTimeoutMs: 15_000,
    authCacheMs: 1000,
    audit: 'off',
    ...overrides,
  }
}

export const secret = () => randomBytes(24).toString('hex')
export const as = session => ({ cookie: `pg_session=${session}` })

/** Plain HTTP (not fetch: undici rewrites the Sec-Fetch-* headers these tests set). */
export function call(base, pathname, { session, headers = {}, method = 'GET', body } = {}) {
  return new Promise((resolve, reject) => {
    const payload = body ? JSON.stringify(body) : undefined
    const req = http.request(`${base}${pathname}`, {
      method, headers: { ...(session ? as(session) : {}), ...headers, ...(payload ? { 'content-type': 'application/json' } : {}) },
    }, res => {
      let text = ''
      res.setEncoding('utf8')
      res.on('data', chunk => { text += chunk })
      res.on('end', () => {
        let parsed = null
        try { parsed = JSON.parse(text) } catch {}
        resolve({ status: res.statusCode, headers: new Headers(Object.entries(res.headers).flatMap(([k, v]) => (Array.isArray(v) ? v : [v]).map(item => [k, String(item)]))), body: parsed, text })
      })
    })
    req.on('error', reject)
    req.end(payload)
  })
}

/** Raw WebSocket handshake; resolves with the status and (on 101) the first frame bytes. */
export function upgrade(base, pathname, headers) {
  return new Promise(resolve => {
    const req = http.request(`${base}${pathname}`, { headers: { connection: 'Upgrade', upgrade: 'websocket', 'sec-websocket-version': '13', 'sec-websocket-key': randomBytes(16).toString('base64'), ...headers } })
    req.on('upgrade', (res, socket, head) => {
      const done = data => resolve({ status: res.statusCode, headers: res.headers, greeting: String(data), socket })
      if (head.length) done(head)
      else socket.once('data', done)
    })
    req.on('response', res => { res.resume(); resolve({ status: res.statusCode, headers: res.headers }) })
    req.on('error', error => resolve({ status: 0, error }))
    req.end()
  })
}
