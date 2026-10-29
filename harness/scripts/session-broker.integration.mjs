// Real-DSH isolation evidence for the session broker (not part of `check`:
// it needs the pinned DSH launcher and boots two real DSH Web Hosts).
//
//   PUREGAMMA_DSH_BIN=/abs/path/to/@deepseek-ai/dsh/lib/bin.js \
//     pnpm --dir harness exec tsx scripts/session-broker.integration.mjs
//
// PG_BROKER_IT_BASE_PATH=/harness mounts the broker under a path prefix (the
// default is the origin root, i.e. the dedicated-subdomain layout).
// PG_BROKER_IT_LAUNCHER=systemd|docker starts the real Hosts under that
// launcher (docker also needs PG_BROKER_IT_DOCKER_IMAGE, e.g. python:3.12-slim
// with the host Node mounted read-only) and adds isolation and reaping checks.
// PG_BROKER_IT_BROWSER=1 adds a real-browser step (Playwright from apps/web,
// Chromium at PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH or /usr/bin/chromium):
// the full DSH Web client boots for user A behind the broker's CSP and no
// request leaves the mount prefix.
//
// FastAPI is stubbed in-process (GET /me + the Host-token mint; the real
// endpoint is covered by tests/security/test_dsh_host_tokens.py). Everything
// else is real: the PureGamma profile + multi-tenant overlay on
// @deepseek-ai/dsh@0.1.7-rc.1, the launch-token exchange, DSH's Host/Origin
// fence, the Session store, the directoryPicker Remote and the WebSocket mux.
import assert from 'node:assert/strict'
import { randomBytes } from 'node:crypto'
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
import http from 'node:http'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { createBroker, defaultContentSecurityPolicy, hostPaths, loadConfig } from '../packages/session-broker/src/index.ts'

const dshBin = process.env.PUREGAMMA_DSH_BIN
if (!dshBin || !existsSync(dshBin)) {
  console.error('set PUREGAMMA_DSH_BIN to the pinned DSH launcher (lib/bin.js)')
  process.exit(2)
}
// Two real Hosts on a shared machine: refuse to start without headroom.
const availableMb = Number(/MemAvailable:\s+(\d+)/.exec(readFileSync('/proc/meminfo', 'utf8'))?.[1] ?? 0) / 1024
if (availableMb < Number(process.env.PG_BROKER_IT_MIN_MB ?? 2000)) {
  console.error(`only ${Math.round(availableMb)} MB available; not starting two DSH Hosts`)
  process.exit(3)
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
  hostHeapMb: Number(process.env.PG_BROKER_IT_HOST_HEAP_MB ?? 512),
  basePath: process.env.PG_BROKER_IT_BASE_PATH ?? '',
  launcher: process.env.PG_BROKER_IT_LAUNCHER ?? 'direct',
  instance: `it${randomBytes(3).toString('hex')}`,
  dockerImage: process.env.PG_BROKER_IT_DOCKER_IMAGE ?? '',
  dockerNode: process.execPath,
  audit: '',
}
config.audit = path.join(root, 'audit.jsonl')
// Loose enough for a real browser boot (~30 parallel requests), tight enough to trip in the flood step.
config.limits = { ...config.limits, userBurst: 80, userRatePerSec: 20, userMaxInflight: 32 }
config.hostLimits = { ...config.hostLimits, memoryMb: config.hostHeapMb + 512, cpuPercent: 100, tasksMax: 128, nofile: 2048, fileSizeMb: 64 }
console.log(`# launcher ${config.launcher}`)
const broker = createBroker(config, { log: message => console.log(`  [broker] ${message}`) })
await new Promise(resolve => broker.server.listen(Number(process.env.PG_BROKER_IT_PORT ?? 0), '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${broker.server.address().port}`
// A browser can only be same-origin with the broker's real address.
config.publicOrigin = origin
config.contentSecurityPolicy = defaultContentSecurityPolicy(origin)
const base = `${origin}${config.basePath}`
console.log(`# broker at ${base}/`)

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
    assert.equal((await rpc('forged', 'session/list', { _request: {} })).status, 401)
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
    // A blank Session is not persisted until it has an event; a title is one.
    const renamed = await rpc('sess-a', 'session/rename', { request: { sessionId: sessionA, title: 'A private plan' } })
    assert.equal(renamed.body?.result?.ok, true, flat(renamed.body))
    const listA = await rpc('sess-a', 'session/list', { _request: {} })
    const listB = await rpc('sess-b', 'session/list', { _request: {} })
    assert.equal(listA.status, 200, flat(listA.body))
    assert.equal(listB.status, 200, flat(listB.body))
    console.log(`  A list: ${flat(listA.body).slice(0, 300)}\n  B list: ${flat(listB.body).slice(0, 300)}`)
    assert.equal(listA.body?.result?.ok, true, flat(listA.body))
    assert.equal(listB.body?.result?.ok, true, flat(listB.body))
    assert.ok(flat(listA.body).includes(sessionA), 'A sees its Session')
    assert.ok(!flat(listB.body).includes('A private plan'), 'B must not see A\'s title')
    assert.ok(!flat(listB.body).includes(sessionA), 'B must not see A\'s Session')
  })

  await step('B cannot rename A\'s Session by id', async () => {
    const hijack = await rpc('sess-b', 'session/rename', { request: { sessionId: sessionA, title: 'owned by B' } })
    assert.notEqual(hijack.body?.result?.ok, true, flat(hijack.body))
    const listA = await rpc('sess-a', 'session/list', { _request: {} })
    assert.ok(!flat(listA.body).includes('owned by B'))
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
  await step('flooding A\'s real Host draws 429 + Retry-After for A only; B keeps working', async () => {
    const flood = await Promise.all(Array.from({ length: 150 }, () => rpc('sess-a', 'session/list', { _request: {} })))
    const during = await rpc('sess-b', 'session/list', { _request: {} })
    const statuses = flood.reduce((count, answer) => ({ ...count, [answer.status]: (count[answer.status] ?? 0) + 1 }), {})
    console.log(`  A flood statuses: ${JSON.stringify(statuses)}; B during flood: ${during.status}`)
    assert.ok((statuses[429] ?? 0) > 0, 'A is limited')
    assert.ok((statuses[200] ?? 0) > 0, 'A is not locked out')
    assert.deepEqual(Object.keys(statuses).filter(status => !['200', '429'].includes(status)), [])
    assert.equal(during.status, 200, 'B unaffected')
    const limited = flood.find(answer => answer.status === 429)
    assert.match(String(limited.body?.error), /rate-limited|too-many-requests/)
    await new Promise(resolve => setTimeout(resolve, 4000))
    assert.equal((await rpc('sess-a', 'session/list', { _request: {} })).status, 200, 'A recovers')
  })

  await step('the audit log records hashed users, Session ids, RPC plugin and trace ids, and no credentials or user content', async () => {
    const lines = readFileSync(config.audit, 'utf8').trim().split('\n').map(line => JSON.parse(line))
    const text = JSON.stringify(lines)
    for (const forbidden of ['sess-a', 'sess-b', 'user-a', 'user-b', 'host.user', 'pg_session', 'dsh-auth', 'A private plan', 'owned by B', SECRET]) {
      assert.ok(!text.includes(forbidden), `audit contains ${forbidden}`)
    }
    const renames = lines.filter(line => line.action === 'rpc:session/rename')
    assert.ok(renames.some(line => line.session === sessionA && line.plugin === 'session' && line.status === 200), JSON.stringify(renames))
    assert.ok(lines.some(line => line.event === 'limit' && line.status === 429))
    assert.ok(lines.some(line => line.action === 'host:start' && line.result === 'ok'))
    assert.ok(lines.every(line => /^[0-9a-f]{24}$/.test(line.user ?? '0'.repeat(24)) && typeof line.trace === 'string'))
    console.log(`  ${lines.length} audit lines; e.g. ${JSON.stringify(renames[0])}`)
  })

  if (config.launcher !== 'direct') {
    await step(`${config.launcher}: each real Host runs under its own kernel limits and sees only its own directory`, async () => {
      const launched = broker.hosts.launched()
      assert.equal(launched.length, 2)
      for (const { userKey: key, name } of launched) {
        let visible
        if (config.launcher === 'systemd') {
          const show = Object.fromEntries(execFileSync('systemctl', ['--user', 'show', name, '-p', 'MainPID,MemoryMax,TasksMax,CPUQuotaPerSecUSec,LimitNOFILE,LimitFSIZE,NoNewPrivileges,PrivateUsers,ProtectSystem'], { encoding: 'utf8' })
            .trim().split('\n').map(line => line.split(/=(.*)/s).slice(0, 2)))
          console.log(`  ${name}: ${JSON.stringify(show)}`)
          assert.equal(show.MemoryMax, String(config.hostLimits.memoryMb * 1024 * 1024))
          assert.equal(show.TasksMax, String(config.hostLimits.tasksMax))
          assert.equal(show.CPUQuotaPerSecUSec, '1s')
          assert.equal(show.LimitNOFILE, String(config.hostLimits.nofile))
          assert.equal(show.LimitFSIZE, String(config.hostLimits.fileSizeMb * 1024 * 1024))
          assert.equal(show.NoNewPrivileges, 'yes')
          assert.equal(show.ProtectSystem, 'strict')
          // The Host's own view of the filesystem, through its mount namespace.
          const pids = execFileSync('systemctl', ['--user', 'show', name, '-p', 'ControlGroup', '--value'], { encoding: 'utf8' }).trim()
          const pid = readFileSync(path.join('/sys/fs/cgroup', pids, 'cgroup.procs'), 'utf8').trim().split('\n').at(-1)
          visible = readdirSync(`/proc/${pid}/root${config.hostsRoot}`)
          assert.throws(() => readdirSync(`/proc/${pid}/root/data/home`), /ENOENT/)
        } else {
          const inspect = JSON.parse(execFileSync('docker', ['inspect', name], { encoding: 'utf8' }))[0].HostConfig
          console.log(`  ${name}: ${JSON.stringify({ Memory: inspect.Memory, NanoCpus: inspect.NanoCpus, PidsLimit: inspect.PidsLimit, ReadonlyRootfs: inspect.ReadonlyRootfs, CapDrop: inspect.CapDrop, SecurityOpt: inspect.SecurityOpt, Ulimits: inspect.Ulimits })}`)
          assert.equal(inspect.Memory, config.hostLimits.memoryMb * 1024 * 1024)
          assert.equal(inspect.PidsLimit, config.hostLimits.tasksMax)
          assert.equal(inspect.ReadonlyRootfs, true)
          assert.deepEqual(inspect.CapDrop, ['ALL'])
          assert.ok(inspect.SecurityOpt.includes('no-new-privileges'))
          visible = JSON.parse(execFileSync('docker', ['exec', name, process.execPath, '-e', `console.log(JSON.stringify(require('fs').readdirSync(${JSON.stringify(config.hostsRoot)})))`], { encoding: 'utf8' }))
        }
        assert.deepEqual(visible, [key], `${name} sees only its own directory`)
      }
    })
  }

  if (process.env.PG_BROKER_IT_BROWSER === '1') {
    await step('a real browser boots the full DSH Web client for A behind the CSP, inside the mount prefix', async () => {
      const { chromium } = createRequire(path.join(harness, '..', 'apps', 'web', 'package.json'))('@playwright/test')
      const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ?? '/usr/bin/chromium', headless: true })
      try {
        const context = await browser.newContext()
        await context.addCookies([{ name: 'pg_session', value: 'sess-a', url: origin }])
        const page = await context.newPage()
        const requests = []
        const problems = []
        const sockets = []
        page.on('request', request => requests.push(request.url()))
        page.on('websocket', socket => sockets.push(socket.url()))
        page.on('console', message => { if (message.type() === 'error') problems.push(message.text()) })
        page.on('pageerror', error => problems.push(String(error)))
        await page.goto(`${base}/`, { waitUntil: 'domcontentloaded', timeout: 60_000 })
        const statuses = []
        page.on('response', response => { if (response.status() >= 400) statuses.push(`${response.status()} ${response.url()}`) })
        try {
          await page.getByText('New Session').first().waitFor({ timeout: 60_000 })
        } catch (error) {
          console.log(`  page text: ${(await page.locator('body').innerText().catch(() => '')).slice(0, 300)}`)
          console.log(`  failed responses: ${statuses.slice(0, 10).join(' | ')}`)
          console.log(`  console errors: ${problems.slice(0, 5).join(' | ').slice(0, 1500)}`)
          throw error
        }
        await page.waitForTimeout(3000)
        const socketOrigin = origin.replace(/^http/, 'ws')
        const escaped = [
          ...requests.filter(url => { const u = new URL(url); return u.origin !== origin || !u.pathname.startsWith(`${config.basePath}/`) }),
          ...sockets.filter(url => !url.startsWith(`${socketOrigin}${config.basePath}/`)),
        ]
        console.log(`  browser: ${requests.length} requests + ${sockets.length} WebSocket(s) [${sockets.map(url => new URL(url).pathname).join(', ')}], ${escaped.length} outside ${config.basePath || '/'}, ${problems.length} console errors`)
        assert.deepEqual(escaped, [])
        assert.deepEqual(problems.filter(text => /did not activate|Content Security Policy|Refused to/i.test(text)), [])
        assert.ok(sockets.some(url => url.endsWith(`${config.basePath}/api/remote.mux`)), 'the Remote WebSocket mux was opened under the prefix')
        assert.ok(!(await page.content()).includes('?token='), 'no launch token in the page')
      } finally {
        await browser.close()
      }
    })
  }
  await step('a logout notification closes B\'s WebSocket and stops B\'s Host; A keeps working', async () => {
    const socket = await new Promise(resolve => {
      const req = http.request(`${base}/api/remote.mux`, { headers: { ...as('sess-b'), origin: config.publicOrigin, connection: 'Upgrade', upgrade: 'websocket', 'sec-websocket-version': '13', 'sec-websocket-key': randomBytes(16).toString('base64') } })
      req.on('upgrade', (_res, sock) => resolve(sock))
      req.end()
    })
    const closed = new Promise(resolve => socket.once('close', resolve))
    const revoked = await fetch(`${origin}/__broker/revoke`, { method: 'POST', headers: { 'x-puregamma-broker-secret': SECRET, 'content-type': 'application/json' }, body: JSON.stringify({ user_id: 'user-b' }) })
    assert.equal(revoked.status, 204)
    await closed
    assert.equal(broker.hosts.launched().length, 1)
    assert.equal((await rpc('sess-a', 'session/list', { _request: {} })).status, 200)
  })

  if (config.launcher !== 'direct') {
    await step(`${config.launcher}: idle reaping stops the real Hosts`, async () => {
      const names = broker.hosts.launched().map(entry => entry.name)
      config.idleMs = 0
      await broker.hosts.reap()
      const alive = () => names.filter(name => {
        try {
          return config.launcher === 'systemd'
            ? execFileSync('systemctl', ['--user', 'is-active', name], { encoding: 'utf8' }).trim() === 'active'
            : execFileSync('docker', ['ps', '-q', '--filter', `name=^${name}$`], { encoding: 'utf8' }).trim() !== ''
        } catch { return false }
      })
      for (let i = 0; i < 100 && alive().length; i++) await new Promise(resolve => setTimeout(resolve, 100))
      assert.deepEqual(alive(), [])
      assert.equal(broker.hosts.size, 0)
    })
  }
} finally {
  await broker.close()
  api.close()
  if (process.env.PG_BROKER_IT_KEEP !== 'true') rmSync(root, { recursive: true, force: true })
}
const failed = results.filter(([status]) => status !== 'ok').length
console.log(`# pass ${results.length - failed}\n# fail ${failed}`)
process.exit(failed ? 1 : 0)
