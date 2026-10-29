import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import { createBroker, defaultContentSecurityPolicy, isNavigation, loadConfig, routeRequest, validateConfig, withoutLaunchToken } from '../packages/session-broker/src/index.ts'
import { brokerConfig, call, secret, startFakeApi, upgrade } from './fixtures/broker-harness.mjs'

// Ingress contract of the session broker: what is routed at all (mount
// prefix), what a browser may do cross-site (top-level navigation only), and
// the headers every answer carries. Caddy in front of it is covered by
// ingress-caddy.test.mjs; real DSH Web under a prefix by
// session-broker.integration.mjs.

const harness = process.cwd()
const root = mkdtempSync(path.join(tmpdir(), 'pg-broker-ingress-'))
const SECRET = secret()
const api = await startFakeApi({ secret: SECRET })
const config = brokerConfig({ api, root, harness, secret: SECRET, basePath: '/harness', loginUrl: 'https://app.puregamma.test/en/auth/login?next=harness' })
config.contentSecurityPolicy = defaultContentSecurityPolicy(config.publicOrigin)
const broker = createBroker(config, { log: () => {} })
await new Promise(resolve => broker.server.listen(0, '127.0.0.1', resolve))
const base = `http://127.0.0.1:${broker.server.address().port}`
const origin = { origin: config.publicOrigin }
const navigation = { 'sec-fetch-mode': 'navigate', 'sec-fetch-dest': 'document' }
test.after(async () => {
  await broker.close()
  await api.close()
  rmSync(root, { recursive: true, force: true })
})

test('routing: nothing outside the mount prefix, bare prefix redirects, launch token stripped', () => {
  assert.deepEqual(routeRequest('/api/session/list', ''), { kind: 'host', path: '/api/session/list' })
  assert.deepEqual(routeRequest('/harness', '/harness'), { kind: 'redirect', location: '/harness/' })
  assert.deepEqual(routeRequest('/harness?x=1', '/harness'), { kind: 'redirect', location: '/harness/?x=1' })
  assert.deepEqual(routeRequest('/harness/api/remote.mux?token=t&a=1', '/harness'), { kind: 'host', path: '/api/remote.mux?a=1' })
  // DSH combo bundle URLs pass through byte-for-byte.
  const combo = '/harness/plugins/??@deepseek-ai/dsh-client-modules/client.js,@puregamma/x/client.js&rev=bff8fd5f046d'
  assert.deepEqual(routeRequest(combo, '/harness'), { kind: 'host', path: combo.slice('/harness'.length) })
  assert.equal(withoutLaunchToken('??a/client.js,b/client.js&token=t&rev=1'), '??a/client.js,b/client.js&rev=1')
  assert.equal(withoutLaunchToken('?token=a&TOKEN=b&%74oken=c&tokenx=d'), '?TOKEN=b&tokenx=d')
  assert.equal(withoutLaunchToken('?token=a'), '')
  for (const outside of ['/', '/harnessx/api', '/api/session/list', '/en/chat', '/harness-evil/']) {
    assert.deepEqual(routeRequest(outside, '/harness'), { kind: 'not-found' }, outside)
  }
  assert.ok(validateConfig({ ...config, basePath: 'harness' }).some(error => /BASE_PATH/.test(error)))
  assert.ok(validateConfig({ ...config, basePath: '/a/../b?' }).some(error => /BASE_PATH/.test(error)))
  assert.ok(validateConfig({ ...config, loginUrl: 'javascript:alert(1)' }).some(error => /LOGIN_URL/.test(error)))
  assert.deepEqual(validateConfig(config), [])
  assert.equal(loadConfig({}).basePath, '', 'root mount by default (dedicated subdomain)')
  assert.equal(loadConfig({ PUREGAMMA_DSH_BASE_PATH: '/harness/' }).basePath, '/harness')
})

test('outside the prefix: 404 before any identity check or Host start', async () => {
  const before = api.calls.length
  assert.equal((await call(base, '/api/session/list', { session: 'sess-a', headers: origin })).status, 404)
  assert.equal((await call(base, '/en/chat', { session: 'sess-a' })).status, 404)
  assert.equal((await upgrade(base, '/api/remote.mux', { cookie: 'pg_session=sess-a', ...origin })).status, 404)
  assert.equal(api.calls.length, before, 'no /me call')
  assert.equal(broker.hosts.size, 0)
  const bare = await call(base, '/harness')
  assert.equal(bare.status, 308)
  assert.equal(bare.headers.get('location'), '/harness/')
})

test('unauthenticated: 401 for fetches, RPCs and WebSockets; a navigation gets a sign-in link', async () => {
  assert.equal((await call(base, '/harness/api/session/list', { method: 'POST', headers: origin })).status, 401)
  assert.equal((await call(base, '/harness/api/session/list', { method: 'POST', session: 'forged', headers: origin })).status, 401)
  assert.equal((await upgrade(base, '/harness/api/remote.mux', origin)).status, 401)
  const page = await call(base, '/harness/', { headers: navigation })
  assert.equal(page.status, 401)
  assert.match(page.headers.get('content-type'), /text\/html/)
  assert.match(page.text, /href="https:\/\/app\.puregamma\.test\/en\/auth\/login\?next=harness"/)
  assert.equal(broker.hosts.size, 0)
})

test('cross-site: fetches, RPCs and WebSockets are 403; a top-level navigation reaches the user\'s Host', async () => {
  const crossSite = { 'sec-fetch-site': 'cross-site' }
  assert.equal((await call(base, '/harness/api/session/list', { method: 'POST', session: 'sess-a', headers: crossSite })).status, 403)
  assert.equal((await call(base, '/harness/api/session/list', { method: 'POST', session: 'sess-a', headers: { origin: 'https://evil.test' } })).status, 403)
  // A navigation is only a navigation without an Origin and as GET.
  assert.equal((await call(base, '/harness/api/debug', { method: 'POST', session: 'sess-a', headers: { ...crossSite, ...navigation } })).status, 403)
  assert.equal((await call(base, '/harness/api/debug', { session: 'sess-a', headers: { ...crossSite, ...navigation, origin: 'https://evil.test' } })).status, 403)
  assert.equal((await upgrade(base, '/harness/api/remote.mux', { cookie: 'pg_session=sess-a', origin: 'https://evil.test' })).status, 403)
  assert.equal((await upgrade(base, '/harness/api/remote.mux', { cookie: 'pg_session=sess-a', ...crossSite, ...navigation })).status, 403)
  const landed = await call(base, '/harness/api/debug', { session: 'sess-a', headers: { ...crossSite, ...navigation } })
  assert.equal(landed.status, 200)
  assert.match(landed.body.home, /hosts\/[0-9a-f]{32}\/home$/)
  assert.equal(isNavigation({ method: 'GET', headers: { ...navigation } }), true)
  assert.equal(isNavigation({ method: 'GET', headers: { 'sec-fetch-mode': 'cors', 'sec-fetch-dest': 'empty' } }), false)
})

test('signed in: each user reaches their own Host under the prefix, HTTP and WebSocket', async () => {
  const a = await call(base, '/harness/api/debug?x=1', { session: 'sess-a', headers: origin })
  const b = await call(base, '/harness/api/debug', { session: 'sess-b', headers: origin })
  assert.equal(a.status, 200)
  assert.equal(a.body.query, '?x=1', 'prefix stripped, query kept')
  assert.notEqual(a.body.home, b.body.home)
  const ws = await upgrade(base, '/harness/api/remote.mux', { cookie: 'pg_session=sess-b', ...origin })
  assert.equal(ws.status, 101)
  assert.equal(ws.greeting.trim(), `hello from ${b.body.home}`)
  ws.socket.destroy()
})

test('Host redirects stay under the prefix and every answer carries the security headers', async () => {
  const redirect = await call(base, '/harness/api/redirect', { session: 'sess-a', headers: origin })
  assert.equal(redirect.status, 302)
  assert.equal(redirect.headers.get('location'), '/harness/api/debug?from=redirect')
  for (const response of [
    redirect,
    await call(base, '/harness/api/debug', { session: 'sess-a', headers: origin }),
    await call(base, '/harness/api/debug', { headers: origin }),
    await call(base, '/elsewhere'),
  ]) {
    const csp = response.headers.get('content-security-policy')
    assert.match(csp, /frame-ancestors 'none'/)
    assert.match(csp, /connect-src 'self' wss:\/\/harness\.puregamma\.test/)
    assert.match(csp, /object-src 'none'/)
    assert.equal(response.headers.get('x-frame-options'), 'DENY')
    assert.equal(response.headers.get('x-content-type-options'), 'nosniff')
    assert.equal(response.headers.get('referrer-policy'), 'no-referrer')
    assert.equal(response.headers.get('set-cookie'), null)
  }
})
