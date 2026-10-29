import assert from 'node:assert/strict'
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import http from 'node:http'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import { createBroker } from '../packages/session-broker/src/index.ts'
import { brokerConfig, call, secret, startFakeApi, upgrade } from './fixtures/broker-harness.mjs'

// Edge routing for the DSH Session front door.
//
// Always: the production Caddyfile and compose file carry no broker route,
// and the opt-in files are wired the way the runbook says.
// With a caddy binary (CADDY_BIN, or `caddy` on PATH; CI validates the same
// files with the caddy:2-alpine image): `caddy adapt` proves the base config
// has no new route and the opt-in one has exactly one, and a live Caddy in
// front of a broker proves 401 / 403 / own-Host over HTTP and WebSocket, and
// that the base config never reaches the broker.

const harness = process.cwd()
const repo = path.resolve(harness, '..')
const read = file => readFileSync(path.join(repo, file), 'utf8')
const BASE_ENV = { APP_DOMAIN: 'app.puregamma.ai', API_DOMAIN: 'api.puregamma.ai' }
const OPT_ENV = { HARNESS_DOMAIN: 'harness.puregamma.ai', DSH_BROKER_UPSTREAM: 'dsh-broker:3480' }

test('production Caddyfile and compose stay unchanged unless the override is applied', () => {
  const caddyfile = read('Caddyfile')
  assert.doesNotMatch(caddyfile, /import|HARNESS_DOMAIN|DSH_BROKER|harness-sessions|3480/)
  const compose = read('docker-compose.production.yml')
  assert.match(compose, /- \.\/Caddyfile:\/etc\/caddy\/Caddyfile:ro/)
  assert.doesNotMatch(compose, /harness-sessions|HARNESS_DOMAIN|DSH_BROKER/)
  const override = read('docker-compose.harness-sessions.yml')
  assert.match(override, /HARNESS_DOMAIN: \$\{HARNESS_DOMAIN:\?/)
  assert.match(override, /DSH_BROKER_UPSTREAM: \$\{DSH_BROKER_UPSTREAM:\?/)
  assert.match(override, /\.\/Caddyfile:\/etc\/caddy\/Caddyfile\.base:ro/)
  assert.match(override, /\.\/deploy\/caddy\/Caddyfile\.harness-sessions:\/etc\/caddy\/Caddyfile:ro/)
  const entry = read('deploy/caddy/Caddyfile.harness-sessions')
  assert.match(entry, /^import \/etc\/caddy\/Caddyfile\.base$/m)
  assert.match(entry, /^import \/etc\/caddy\/harness-sessions\.caddy$/m)
  const site = read('deploy/caddy/harness-sessions.caddy')
  assert.match(site, /header_up X-Real-IP \{client_ip\}/)
  assert.doesNotMatch(site, /CF-Connecting-IP|X-Forwarded-For/i)
})

function findCaddy() {
  if (process.env.CADDY_BIN) return existsSync(process.env.CADDY_BIN) ? process.env.CADDY_BIN : undefined
  try {
    return execFileSync('sh', ['-c', 'command -v caddy'], { encoding: 'utf8' }).trim() || undefined
  } catch {
    return undefined
  }
}
const caddy = findCaddy()
const skip = caddy ? false : 'no caddy binary (set CADDY_BIN); CI validates the same files with caddy:2-alpine'

/** Copy the deploy files into a scratch /etc/caddy, rewriting the absolute import paths. */
function stage(dir) {
  const etc = path.join(dir, 'etc')
  mkdirSync(etc, { recursive: true })
  writeFileSync(path.join(etc, 'Caddyfile.base'), read('Caddyfile'))
  writeFileSync(path.join(etc, 'harness-sessions.caddy'), read('deploy/caddy/harness-sessions.caddy'))
  writeFileSync(path.join(etc, 'Caddyfile'), read('deploy/caddy/Caddyfile.harness-sessions').replaceAll('/etc/caddy/', `${etc}/`))
  return etc
}
const caddyEnv = (dir, extra, base = BASE_ENV) => ({ PATH: process.env.PATH, HOME: dir, XDG_DATA_HOME: dir, XDG_CONFIG_HOME: dir, ...base, ...extra })
/** Live runs: scheme-less sites would still bind the HTTPS port, so the env sites get `http://`. */
const LIVE_ENV = Object.fromEntries(Object.entries(BASE_ENV).map(([name, value]) => [name, `http://${value}`]))
function adapt(dir, file, extra) {
  const out = execFileSync(caddy, ['adapt', '--config', file, '--adapter', 'caddyfile'], { env: caddyEnv(dir, extra), encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
  const routes = Object.values(JSON.parse(out).apps.http.servers).flatMap(server => server.routes ?? [])
  return routes.map(route => ({ hosts: route.match?.[0]?.host ?? [], dials: JSON.stringify(route).match(/"dial":"[^"]+"/g) ?? [] }))
}

test('caddy adapt: base config has no broker route; the opt-in config adds exactly one', { skip }, () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'pg-caddy-'))
  try {
    const etc = stage(dir)
    const base = adapt(dir, path.join(etc, 'Caddyfile.base'), {})
    assert.ok(base.every(route => !route.hosts.includes(OPT_ENV.HARNESS_DOMAIN)))
    assert.ok(base.every(route => !route.dials.some(dial => dial.includes('3480'))))
    const opted = adapt(dir, path.join(etc, 'Caddyfile'), OPT_ENV)
    const added = opted.filter(route => route.hosts.includes(OPT_ENV.HARNESS_DOMAIN))
    assert.equal(added.length, 1)
    assert.deepEqual(added[0].dials, ['"dial":"dsh-broker:3480"'])
    assert.equal(opted.length, base.length + 1, 'nothing else changes')
    // Required variables: Caddy itself would happily adapt `{$HARNESS_DOMAIN}`
    // to an empty site, so the compose override enforces them with `:?`.
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

async function runCaddy(dir, file, port, extra) {
  // auto_https off + high http(s) ports: the production site blocks then serve
  // plain HTTP on one local port, routed by Host, and need no certificates.
  const wrapper = path.join(dir, `run-${port}.caddy`)
  writeFileSync(wrapper, `{\n\tauto_https off\n\tadmin off\n\thttp_port ${port}\n\thttps_port ${port + 1}\n\tpersist_config off\n}\nimport ${file}\n`)
  const child = spawn(caddy, ['run', '--config', wrapper, '--adapter', 'caddyfile'], { env: caddyEnv(dir, extra, LIVE_ENV), stdio: ['ignore', 'ignore', 'pipe'], detached: true })
  let log = ''
  child.stderr.on('data', chunk => { log += chunk })
  for (let i = 0; i < 100; i++) {
    const up = await new Promise(resolve => {
      const req = http.get({ host: '127.0.0.1', port, path: '/', headers: { host: 'nothing.invalid' } }, res => { res.resume(); resolve(true) })
      req.on('error', () => resolve(false))
    })
    if (up) return child
    if (child.exitCode !== null) break
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  child.kill('SIGKILL')
  throw new Error(`caddy did not start:\n${log.slice(-2000)}`)
}
const stopCaddy = child => new Promise(resolve => {
  if (child.exitCode !== null) return resolve()
  child.once('exit', resolve)
  child.kill('SIGTERM')
})

test('live Caddy: 401 signed out, 403 cross-site, own Host over HTTP and WebSocket; base config never reaches the broker', { skip }, async () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'pg-caddy-live-'))
  const SECRET = secret()
  const api = await startFakeApi({ secret: SECRET })
  const port = Number(process.env.PG_INGRESS_CADDY_PORT ?? 3113)
  const config = brokerConfig({ api, root: dir, harness, secret: SECRET, publicOrigin: `http://${OPT_ENV.HARNESS_DOMAIN}:${port}` })
  const seen = []
  const broker = createBroker(config, { log: () => {} })
  broker.server.prependListener('request', request => seen.push(request.url))
  broker.server.prependListener('upgrade', request => seen.push(request.url))
  await new Promise(resolve => broker.server.listen(0, '127.0.0.1', resolve))
  const upstream = `127.0.0.1:${broker.server.address().port}`
  const etc = stage(dir)
  const edge = `http://127.0.0.1:${port}`
  const host = { host: `${OPT_ENV.HARNESS_DOMAIN}:${port}` }
  const origin = { origin: config.publicOrigin }
  let child
  try {
    child = await runCaddy(dir, path.join(etc, 'Caddyfile.base'), port, {})
    const before = seen.length
    const viaBase = await call(edge, '/api/debug', { session: 'sess-a', headers: { ...host, ...origin } })
    assert.notEqual(viaBase.status, 401)
    assert.equal(viaBase.body?.home, undefined)
    assert.equal(seen.length, before, 'the production Caddyfile has no route to the broker')
    await stopCaddy(child)

    child = await runCaddy(dir, path.join(etc, 'Caddyfile'), port, { HARNESS_DOMAIN: `http://${OPT_ENV.HARNESS_DOMAIN}`, DSH_BROKER_UPSTREAM: upstream })
    assert.equal((await call(edge, '/api/session/list', { method: 'POST', headers: { ...host, ...origin } })).status, 401)
    assert.equal((await upgrade(edge, '/api/remote.mux', { ...host, ...origin })).status, 401)
    assert.equal((await call(edge, '/api/session/list', { method: 'POST', session: 'sess-a', headers: { ...host, origin: 'https://evil.test' } })).status, 403)
    assert.equal((await call(edge, '/api/session/list', { method: 'POST', session: 'sess-a', headers: { ...host, 'sec-fetch-site': 'cross-site' } })).status, 403)
    assert.equal((await upgrade(edge, '/api/remote.mux', { ...host, cookie: 'pg_session=sess-a', origin: 'https://evil.test' })).status, 403)
    assert.equal(broker.hosts.size, 0, 'refused requests start no Host')

    const a = await call(edge, '/api/debug', { session: 'sess-a', headers: { ...host, ...origin } })
    const b = await call(edge, '/api/debug', { session: 'sess-b', headers: { ...host, ...origin } })
    assert.equal(a.status, 200)
    assert.notEqual(a.body.home, b.body.home)
    assert.equal(a.body.headers['x-real-ip'], undefined, 'edge headers stop at the broker')
    assert.match(a.body.cookie, /^dsh-auth-/)
    assert.equal(a.headers.get('strict-transport-security'), 'max-age=31536000; includeSubDomains')
    assert.match(a.headers.get('content-security-policy') ?? '', /frame-ancestors 'none'/)
    const ws = await upgrade(edge, '/api/remote.mux', { ...host, cookie: 'pg_session=sess-a', ...origin })
    assert.equal(ws.status, 101)
    assert.equal(ws.greeting.trim(), `hello from ${a.body.home}`)
    ws.socket.destroy()
  } finally {
    if (child) await stopCaddy(child)
    await broker.close()
    await api.close()
    rmSync(dir, { recursive: true, force: true })
  }
})
