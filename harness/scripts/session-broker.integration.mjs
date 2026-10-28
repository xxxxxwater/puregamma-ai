// Real-DSH isolation evidence for the session broker (not part of `check`:
// it needs the pinned DSH launcher and boots two real DSH Web Hosts).
//
//   PUREGAMMA_DSH_BIN=/abs/path/to/@deepseek-ai/dsh/lib/bin.js \
//     pnpm --dir harness exec tsx scripts/session-broker.integration.mjs
//
// FastAPI is stubbed in-process (GET /me + the Host-token mint; the real
// endpoint is covered by tests/security/test_dsh_host_tokens.py). Everything
// else is real: the PureGamma profile + multi-tenant overlay on
// @deepseek-ai/dsh@0.1.7-rc.1, the launch-token exchange, DSH's Host/Origin
// fence, the Session store, the directoryPicker Remote and the WebSocket mux.
import assert from 'node:assert/strict'
import { randomBytes } from 'node:crypto'
import { existsSync, mkdtempSync, readdirSync, rmSync } from 'node:fs'
import http from 'node:http'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { createBroker, hostPaths, loadConfig } from '../packages/session-broker/src/index.ts'

const dshBin = process.env.PUREGAMMA_DSH_BIN
if (!dshBin || !existsSync(dshBin)) {
  console.error('set PUREGAMMA_DSH_BIN to the pinned DSH launcher (lib/bin.js)')
  process.exit(2)
}
const harness = process.cwd()
const SECRET = randomBytes(24).toString('hex')
const USERS = { 'sess-a': 'user-a', 'sess-b': 'user-b' }
const root = mkdtempSync(path.join(tmpdir(), 'pg-broker-it-'))
const results = []
const step = async (name, fn) => {
  try {
    await fn()
    results.push(['ok', name])
    console.log(`ok - ${name}`)
  } catch (error) {
    results.push(['not ok', name])
    console.log(`not ok - ${name}\n  ${String(error?.stack ?? error).split('\n').slice(0, 4).join('\n  ')}`)
  }
}

const api = http.createServer((req, res) => {
  const cookie = /pg_session=([^;]+)/.exec(req.headers.cookie ?? '')?.[1]
  const bearer = /^Bearer (.+)$/.exec(req.headers.authorization ?? '')?.[1]
  const user = USERS[cookie ?? bearer] ?? (bearer?.startsWith('host.') ? bearer.split('.')[1] : undefined)
  const send = (status, body) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)) }
  if (req.url === '/me') return user ? send(200, { user: { id: user } }) : send(401, {})
  if (req.url === '/internal/dsh/host-tokens' && req.headers['x-puregamma-broker-secret'] === SECRET && user) {
    return send(200, { token: `host.${user}.${Date.now()}`, user_id: user, expires_at: Math.floor(Date.now() / 1000) + 600 })
  }
  send(user ? 404 : 401, {})
})
await new Promise(resolve => api.listen(0, '127.0.0.1', resolve))
const apiUrl = `http://127.0.0.1:${api.address().port}`

const config = {
  ...loadConfig({}),
  enabled: true,
  publicOrigin: 'https://app.puregamma.test',
  apiBaseUrl: apiUrl,
  hostApiBaseUrl: apiUrl,
  brokerSecret: SECRET,
  hostsRoot: path.join(root, 'hosts'),
  dshBin,
  profileDir: path.join(harness, 'profile'),
  patchFiles: [path.join(harness, 'profile', 'multi-tenant.patch.yml')],
  maxHosts: 2,
  startTimeoutMs: 180_000,
}
const broker = createBroker(config, { log: message => console.log(`  [broker] ${message}`) })
await new Promise(resolve => broker.server.listen(Number(process.env.PG_BROKER_IT_PORT ?? 0), '127.0.0.1', resolve))
const base = `http://127.0.0.1:${broker.server.address().port}`

const as = session => ({ cookie: `pg_session=${session}` })
let rpcId = 0
async function rpc(session, endpoint, args = {}) {
  const response = await fetch(`${base}/api/${endpoint}`, {
    method: 'POST',
    headers: { ...as(session), origin: config.publicOrigin, 'content-type': 'application/json' },
    body: JSON.stringify({ type: 'client-request', rpcId: String(++rpcId), method: endpoint, payload: { args } }),
  })
  const text = await response.text()
  let body
  try { body = JSON.parse(text) } catch { body = text }
  return { status: response.status, body }
}
function upgrade(headers) {
  return new Promise(resolve => {
    const req = http.request(`${base}/api/remote.mux`, { headers: { connection: 'Upgrade', upgrade: 'websocket', 'sec-websocket-version': '13', 'sec-websocket-key': randomBytes(16).toString('base64'), ...headers } })
    req.on('upgrade', (res, socket) => { socket.destroy(); resolve(res.statusCode) })
    req.on('response', res => { res.resume(); resolve(res.statusCode) })
    req.on('error', () => resolve(0))
    req.end()
  })
}
const flat = value => JSON.stringify(value)

try {
  await step('unauthenticated HTTP, RPC and WebSocket get 401 and start no Host', async () => {
    assert.equal((await fetch(`${base}/`)).status, 401)
    assert.equal((await rpc('forged', 'session/list', { request: {} })).status, 401)
    assert.equal(await upgrade({ origin: config.publicOrigin }), 401)
    assert.equal(broker.hosts.size, 0)
  })

  await step('user A and user B each boot their own real DSH Web Host', async () => {
    const a = await fetch(`${base}/`, { headers: as('sess-a') })
    assert.equal(a.status, 200, 'A index')
    assert.match(await a.text(), /<html/i)
    const b = await fetch(`${base}/`, { headers: as('sess-b') })
    assert.equal(b.status, 200, 'B index')
    assert.equal(broker.hosts.size, 2)
  })

  let sessionA
  await step('a Session created by A is listed for A and never for B', async () => {
    const created = await rpc('sess-a', 'session/create', { request: { cwd: hostPaths(config.hostsRoot, 'user-a').workspace } })
    assert.equal(created.status, 200, flat(created.body))
    sessionA = created.body?.result?.value?.sessionId ?? created.body?.value?.sessionId ?? created.body?.result?.sessionId
    assert.ok(sessionA, `no session id in ${flat(created.body)}`)
    const listA = await rpc('sess-a', 'session/list', { request: {} })
    const listB = await rpc('sess-b', 'session/list', { request: {} })
    assert.equal(listA.status, 200, flat(listA.body))
    assert.equal(listB.status, 200, flat(listB.body))
    assert.ok(flat(listA.body).includes(sessionA), 'A sees its Session')
    assert.ok(!flat(listB.body).includes(sessionA), 'B must not see A\'s Session')
    console.log(`  A list: ${flat(listA.body).slice(0, 200)}\n  B list: ${flat(listB.body).slice(0, 200)}`)
  })

  await step('B cannot read A\'s Session history by id', async () => {
    const page = await rpc('sess-b', 'session/page', { request: { sessionId: sessionA } })
    assert.ok(page.status !== 200 || /error|not.?found|unknown/i.test(flat(page.body)), flat(page.body))
    assert.ok(!flat(page.body).includes(hostPaths(config.hostsRoot, 'user-a').workspace))
  })

  await step('Session stores live under each user\'s own DSH_HOME', () => {
    const homeA = hostPaths(config.hostsRoot, 'user-a').home
    const homeB = hostPaths(config.hostsRoot, 'user-b').home
    assert.notEqual(homeA, homeB)
    assert.ok(existsSync(path.join(homeA, 'sessions')), 'A sessions dir')
    const filesB = existsSync(path.join(homeB, 'sessions')) ? readdirSync(path.join(homeB, 'sessions'), { recursive: true }).map(String) : []
    assert.ok(!filesB.some(file => file.includes(sessionA)), 'A\'s Session never lands in B\'s store')
  })

  await step('the directory picker Remote is confined to the user\'s workspace root', async () => {
    const rootA = hostPaths(config.hostsRoot, 'user-a').workspace
    const rootB = hostPaths(config.hostsRoot, 'user-b').workspace
    const listed = await rpc('sess-a', 'directoryPicker/list', {})
    assert.equal(listed.status, 200, flat(listed.body))
    assert.ok(flat(listed.body).includes(rootA), flat(listed.body))
    for (const escape of ['/', '/etc', rootB, path.join(rootA, '..')]) {
      const denied = await rpc('sess-a', 'directoryPicker/list', { path: escape })
      assert.match(flat(denied.body), /directory-picker\/unreadable/, `${escape}: ${flat(denied.body)}`)
    }
    const created = await rpc('sess-a', 'directoryPicker/createDirectory', { path: rootA, name: 'x' })
    assert.match(flat(created.body), /directory-picker\/create-failed/, flat(created.body))
  })

  await step('the WebSocket mux needs auth and the public Origin, then reaches the caller\'s Host', async () => {
    assert.equal(await upgrade(as('sess-a')), 403)
    assert.equal(await upgrade({ ...as('sess-a'), origin: 'https://evil.test' }), 403)
    assert.equal(await upgrade({ origin: config.publicOrigin }), 401)
    assert.equal(await upgrade({ ...as('sess-a'), origin: config.publicOrigin }), 101)
  })

  await step('cross-site HTTP is refused before any Host sees it', async () => {
    const response = await fetch(`${base}/api/session/list`, { method: 'POST', headers: { ...as('sess-a'), origin: 'https://evil.test' } })
    assert.equal(response.status, 403)
  })
} finally {
  await broker.close()
  api.close()
  if (process.env.PG_BROKER_IT_KEEP !== 'true') rmSync(root, { recursive: true, force: true })
}
const failed = results.filter(([status]) => status !== 'ok').length
console.log(`# pass ${results.length - failed}\n# fail ${failed}`)
process.exit(failed ? 1 : 0)
