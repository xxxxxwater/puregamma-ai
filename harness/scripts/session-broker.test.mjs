import assert from 'node:assert/strict'
import { randomBytes } from 'node:crypto'
import { mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs'
import http from 'node:http'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import { createBroker, hostEnv, hostPaths, loadConfig, validateConfig } from '../packages/session-broker/src/index.ts'

// Multi-tenant DSH front door. A fake FastAPI and a fake DSH host with the real
// outward contract (ready line, launch-token cookie, loopback Host/Origin
// fence, DSH_HOME Session store) prove: unauthenticated requests never get a
// Host, each user reaches only their own Host, the WebSocket needs auth and
// the public Origin, credentials never cross into a Host, and caps/reaping hold.
// `session-broker.integration.mjs` repeats the isolation checks on real DSH Web.

const harness = process.cwd()
const fakeHost = path.join(harness, 'scripts', 'fixtures', 'fake-dsh-host.mjs')
const SECRET = randomBytes(24).toString('hex')
const SESSIONS = { 'sess-a': 'user-a', 'sess-b': 'user-b', 'sess-c': 'user-c', 'sess-evil': 'user-evil' }
const root = mkdtempSync(path.join(tmpdir(), 'pg-broker-'))
let mints = 0

const api = http.createServer((req, res) => {
  const cookie = /pg_session=([^;]+)/.exec(req.headers.cookie ?? '')?.[1]
  const bearer = /^Bearer (.+)$/.exec(req.headers.authorization ?? '')?.[1]
  const user = SESSIONS[cookie ?? bearer] ?? (bearer?.startsWith('host.') ? bearer.split('.')[1] : undefined)
  const send = (status, body) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)) }
  if (req.url === '/me') return user ? send(200, { user: { id: user } }) : send(401, { detail: 'no' })
  if (req.url === '/internal/dsh/host-tokens' && req.method === 'POST') {
    if (req.headers['x-puregamma-broker-secret'] !== SECRET) return send(403, {})
    if (!user) return send(401, {})
    mints += 1
    // user-evil simulates a faulty API that answers for someone else.
    const owner = user === 'user-evil' ? 'user-a' : user
    return send(200, { token: `host.${owner}.${mints}`, user_id: owner, expires_at: Math.floor(Date.now() / 1000) + 600 })
  }
  send(404, {})
})
await new Promise(resolve => api.listen(0, '127.0.0.1', resolve))

const config = {
  ...loadConfig({}),
  enabled: true,
  publicOrigin: 'https://app.puregamma.test',
  apiBaseUrl: `http://127.0.0.1:${api.address().port}`,
  hostApiBaseUrl: `http://127.0.0.1:${api.address().port}`,
  brokerSecret: SECRET,
  hostsRoot: path.join(root, 'hosts'),
  dshBin: fakeHost,
  profileDir: harness,
  patchFiles: [],
  maxHosts: 2,
  idleMs: 60_000,
  startTimeoutMs: 15_000,
  authCacheMs: 1000,
}
const broker = createBroker(config, { log: () => {} })
await new Promise(resolve => broker.server.listen(0, '127.0.0.1', resolve))
const base = `http://127.0.0.1:${broker.server.address().port}`
test.after(async () => {
  await broker.close()
  api.close()
  rmSync(root, { recursive: true, force: true })
})

const as = session => ({ cookie: `pg_session=${session}; theme=dark` })
async function call(pathname, { session, headers = {}, method = 'POST', body } = {}) {
  const response = await fetch(`${base}${pathname}`, {
    method, headers: { ...(session ? as(session) : {}), ...headers, ...(body ? { 'content-type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined, redirect: 'manual',
  })
  return { status: response.status, headers: response.headers, body: await response.json().catch(() => null) }
}
function upgrade(headers) {
  return new Promise(resolve => {
    const req = http.request(`${base}/api/remote.mux`, { headers: { connection: 'Upgrade', upgrade: 'websocket', 'sec-websocket-version': '13', 'sec-websocket-key': randomBytes(16).toString('base64'), ...headers } })
    req.on('upgrade', (res, socket, head) => {
      const done = data => resolve({ status: res.statusCode, greeting: String(data), socket })
      if (head.length) done(head)
      else socket.once('data', done)
    })
    req.on('response', res => { res.resume(); resolve({ status: res.statusCode }) })
    req.end()
  })
}

test('the broker is off unless enabled and refuses weak configuration', () => {
  const defaults = loadConfig({})
  assert.equal(defaults.enabled, false)
  assert.equal(defaults.listenHost, '127.0.0.1')
  assert.ok(validateConfig(defaults).some(error => /ENABLED/.test(error)))
  assert.ok(validateConfig({ ...config, brokerSecret: 'short' }).some(error => /SECRET/.test(error)))
  assert.deepEqual(validateConfig(config), [])
})

test('unauthenticated HTTP and WebSocket requests get 401 and no Host', async () => {
  assert.equal((await call('/api/session/list')).status, 401)
  assert.equal((await call('/api/session/list', { session: 'forged' })).status, 401)
  assert.equal((await upgrade({ origin: config.publicOrigin })).status, 401)
  assert.equal(broker.hosts.size, 0)
})

test('each user reaches only their own Host and Session store', async () => {
  assert.equal((await call('/api/session/create', { session: 'sess-a', body: { title: 'A private plan' } })).status, 200)
  assert.equal((await call('/api/session/create', { session: 'sess-b', body: { title: 'B private plan' } })).status, 200)
  const listA = await call('/api/session/list', { session: 'sess-a' })
  const listB = await call('/api/session/list', { session: 'sess-b' })
  assert.deepEqual(listA.body.sessions, ['A private plan'])
  assert.deepEqual(listB.body.sessions, ['B private plan'])
  // Bearer credentials resolve to the same user's Host.
  assert.deepEqual((await call('/api/session/list', { headers: { authorization: 'Bearer sess-a' } })).body.sessions, ['A private plan'])

  const debugA = (await call('/api/debug', { session: 'sess-a' })).body
  const debugB = (await call('/api/debug', { session: 'sess-b' })).body
  assert.notEqual(debugA.home, debugB.home)
  assert.equal(debugA.home, hostPaths(config.hostsRoot, 'user-a').home)
  assert.equal(debugA.cwd, hostPaths(config.hostsRoot, 'user-a').workspace)
  assert.equal(debugA.workspaceRoot, debugA.cwd)
})

test('user credentials, shared secrets and the launch token never reach a Host', async () => {
  process.env.PUREGAMMA_LEGACY_API_TOKEN = 'shared-operator-token'
  const debug = (await call('/api/debug?token=stolen&x=1', { session: 'sess-a', headers: { origin: config.publicOrigin } })).body
  delete process.env.PUREGAMMA_LEGACY_API_TOKEN
  assert.match(debug.cookie, /^dsh-auth-test=/)
  assert.doesNotMatch(debug.cookie, /pg_session|theme/)
  assert.equal(debug.authorization, null)
  assert.equal(debug.query, '?x=1')
  assert.equal(debug.sharedToken, null)
  assert.equal(debug.brokerSecret, null)
  const env = hostEnv({ ...config, envPassthrough: ['PUREGAMMA_LEGACY_API_TOKEN', 'DSH_BROKER_SECRET'] }, hostPaths(config.hostsRoot, 'x'), { PUREGAMMA_LEGACY_API_TOKEN: 't', DSH_BROKER_SECRET: 's', PATH: '/bin' })
  assert.equal(env.PUREGAMMA_LEGACY_API_TOKEN, undefined)
  assert.equal(env.DSH_BROKER_SECRET, undefined)
  // Host cookies stay in the broker.
  assert.equal((await call('/api/session/list', { session: 'sess-a' })).headers.get('set-cookie'), null)
})

test('each Host gets its own user-scoped legacy-api token file, mode 0600', () => {
  for (const user of ['user-a', 'user-b']) {
    const file = hostPaths(config.hostsRoot, user).tokenFile
    assert.match(readFileSync(file, 'utf8').trim(), new RegExp(`^host\\.${user}\\.\\d+$`))
    assert.equal(statSync(file).mode & 0o077, 0)
  }
})

test('cross-site requests and WebSockets without the public Origin are refused', async () => {
  assert.equal((await call('/api/session/list', { session: 'sess-a', headers: { origin: 'https://evil.test' } })).status, 403)
  assert.equal((await call('/api/session/list', { session: 'sess-a', headers: { 'sec-fetch-site': 'cross-site' } })).status, 403)
  assert.equal((await upgrade(as('sess-a'))).status, 403)
  assert.equal((await upgrade({ ...as('sess-a'), origin: 'https://evil.test' })).status, 403)
})

test('an authenticated WebSocket is tunnelled to the caller\'s own Host only', async () => {
  const a = await upgrade({ ...as('sess-a'), origin: config.publicOrigin })
  const b = await upgrade({ ...as('sess-b'), origin: config.publicOrigin })
  assert.equal(a.status, 101)
  assert.equal(a.greeting.trim(), `hello from ${hostPaths(config.hostsRoot, 'user-a').home}`)
  assert.equal(b.greeting.trim(), `hello from ${hostPaths(config.hostsRoot, 'user-b').home}`)
  // Both Hosts are busy (open sockets), so a third user hits the cap.
  assert.equal((await call('/api/session/list', { session: 'sess-c' })).status, 503)
  a.socket.destroy()
  b.socket.destroy()
  for (let i = 0; i < 50 && broker.hosts.stats().openSockets > 0; i++) await new Promise(resolve => setTimeout(resolve, 50))
  assert.equal(broker.hosts.stats().openSockets, 0, 'closing the browser socket closes the tunnel')
  // Under pressure the least recently used idle Host is stopped for the newcomer.
  const newcomer = await call('/api/session/list', { session: 'sess-c' })
  assert.equal(newcomer.status, 200, JSON.stringify(newcomer.body))
  assert.equal(broker.hosts.size, 2)
})

test('a token minted for a different user is discarded and no Host starts', async () => {
  const before = broker.hosts.size
  assert.equal((await call('/api/session/list', { session: 'sess-evil' })).status, 503)
  assert.ok(broker.hosts.size <= before)
})

test('idle Hosts are reaped and their token files removed', async () => {
  const file = hostPaths(config.hostsRoot, 'user-c').tokenFile
  config.idleMs = 0
  await broker.hosts.reap()
  assert.equal(broker.hosts.size, 0)
  assert.throws(() => statSync(file))
})
