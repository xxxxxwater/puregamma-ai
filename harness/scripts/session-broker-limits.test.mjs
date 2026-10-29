import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import test from 'node:test'
import { Concurrency, KeyedBuckets, TokenBucket, createBroker, identifiersOf, traceOf } from '../packages/session-broker/src/index.ts'
import { brokerConfig, call, secret, startFakeApi, upgrade } from './fixtures/broker-harness.mjs'

// Stage 3: admission control (per-user rate and concurrency, per-address
// identity lookups, global Host start rate), the audit log, trace
// propagation, and logout linkage (revoke endpoint + socket revalidation).
// Every limit is shown to refuse the noisy user with 429 + Retry-After while
// another user keeps getting 200.

const harness = process.cwd()
const root = mkdtempSync(path.join(tmpdir(), 'pg-broker-limits-'))
const SECRET = secret()
const sessions = { 'sess-a': 'user-a', 'sess-b': 'user-b', 'sess-c': 'user-c', 'sess-d': 'user-d' }
const api = await startFakeApi({ secret: SECRET, sessions })
const lines = []
test.after(async () => {
  await api.close()
  rmSync(root, { recursive: true, force: true })
})

let instance = 0
async function withBroker({ limits = {}, ...overrides }, fn) {
  const config = brokerConfig({ api, root, harness, secret: SECRET, hostsRoot: path.join(root, `hosts-${++instance}`), ...overrides })
  config.limits = { ...config.limits, ...limits }
  const broker = createBroker(config, { log: () => {}, auditSink: line => lines.push(JSON.parse(line)) })
  await new Promise(resolve => broker.server.listen(0, '127.0.0.1', resolve))
  try {
    await fn(broker, `http://127.0.0.1:${broker.server.address().port}`, config)
  } finally {
    await broker.close()
  }
}
const get = (url, config, session, pathname = '/api/debug', headers = {}) => call(url, pathname, { session, headers: { origin: config.publicOrigin, ...headers } })

test('token bucket, keyed buckets and concurrency counters', () => {
  let now = 0
  const bucket = new TokenBucket(2, 1, () => now)
  assert.ok(bucket.take().ok)
  assert.ok(bucket.take().ok)
  assert.deepEqual(bucket.take(), { ok: false, retryAfterSec: 1 })
  now = 1000
  assert.ok(bucket.take().ok)
  const slow = new TokenBucket(1, 0.5, () => now)
  slow.take()
  assert.deepEqual(slow.take(), { ok: false, retryAfterSec: 2 })
  const keyed = new KeyedBuckets(1, 1, 3, () => now)
  assert.ok(keyed.take('a').ok)
  assert.ok(!keyed.take('a').ok)
  assert.ok(keyed.take('b').ok, 'keys are independent')
  for (const key of ['c', 'd', 'e']) keyed.take(key)
  assert.ok(keyed.size <= 3, 'bounded number of keys')
  const slots = new Concurrency(1)
  const release = slots.acquire('a')
  assert.equal(slots.acquire('a'), undefined)
  assert.ok(slots.acquire('b'))
  release()
  release()
  assert.equal(slots.count('a'), 0)
})

test('per-user request rate: the flooding user gets 429 + Retry-After, another user is unaffected', async () => {
  await withBroker({ limits: { userBurst: 5, userRatePerSec: 1 }, authCacheMs: 60_000 }, async (_broker, url, config) => {
    const answers = []
    for (let i = 0; i < 8; i++) answers.push(await get(url, config, 'sess-a'))
    const limited = answers.filter(answer => answer.status === 429)
    assert.ok(limited.length >= 2, answers.map(answer => answer.status).join(','))
    assert.equal(limited[0].body.error, 'rate-limited')
    assert.ok(Number(limited[0].headers.get('retry-after')) >= 1)
    assert.equal((await get(url, config, 'sess-b')).status, 200)
    assert.ok(lines.some(line => line.event === 'limit' && line.result === 'rate-limited' && line.status === 429))
  })
})

test('per-user in-flight requests and WebSockets are capped per user', async () => {
  await withBroker({ limits: { userMaxInflight: 2, userMaxSockets: 1 }, authCacheMs: 60_000 }, async (_broker, url, config) => {
    assert.equal((await get(url, config, 'sess-a')).status, 200, 'Host up')
    const slow = [get(url, config, 'sess-a', '/api/slow?ms=800'), get(url, config, 'sess-a', '/api/slow?ms=800')]
    await new Promise(resolve => setTimeout(resolve, 150))
    const third = await get(url, config, 'sess-a', '/api/slow?ms=10')
    assert.equal(third.status, 429)
    assert.equal(third.body.error, 'too-many-requests')
    assert.equal(third.headers.get('retry-after'), '1')
    assert.equal((await get(url, config, 'sess-b', '/api/slow?ms=10')).status, 200, 'B unaffected')
    assert.deepEqual((await Promise.all(slow)).map(answer => answer.status), [200, 200])
    assert.equal((await get(url, config, 'sess-a', '/api/slow?ms=10')).status, 200, 'slots are released')

    const ws = { origin: config.publicOrigin }
    const first = await upgrade(url, '/api/remote.mux', { cookie: 'pg_session=sess-a', ...ws })
    assert.equal(first.status, 101)
    const second = await upgrade(url, '/api/remote.mux', { cookie: 'pg_session=sess-a', ...ws })
    assert.equal(second.status, 429)
    const other = await upgrade(url, '/api/remote.mux', { cookie: 'pg_session=sess-b', ...ws })
    assert.equal(other.status, 101, 'B unaffected')
    first.socket.destroy()
    other.socket.destroy()
    await new Promise(resolve => setTimeout(resolve, 100))
    const again = await upgrade(url, '/api/remote.mux', { cookie: 'pg_session=sess-a', ...ws })
    assert.equal(again.status, 101, 'socket slot released on close')
    again.socket.destroy()
  })
})

test('identity lookups that miss the cache are limited per client address, not globally', async () => {
  await withBroker({ limits: { ipLookupBurst: 3, ipLookupRatePerSec: 1 }, clientIpHeader: 'x-real-ip', authCacheMs: 60_000 }, async (_broker, url, config) => {
    assert.equal((await get(url, config, 'sess-a', '/api/debug', { 'x-real-ip': '198.51.100.7' })).status, 200)
    const forged = []
    for (let i = 0; i < 5; i++) forged.push((await get(url, config, `forged-${i}`, '/api/debug', { 'x-real-ip': '203.0.113.9' })).status)
    assert.deepEqual(forged.slice(0, 3), [401, 401, 401])
    assert.deepEqual(forged.slice(3), [429, 429], 'FastAPI is not called for the flood')
    // Same address, but a cached credential needs no lookup; other addresses have their own budget.
    assert.equal((await get(url, config, 'sess-a', '/api/debug', { 'x-real-ip': '203.0.113.9' })).status, 200)
    assert.equal((await get(url, config, 'sess-b', '/api/debug', { 'x-real-ip': '198.51.100.8' })).status, 200)
  })
})

test('global Host start rate: new Hosts get 429 + Retry-After, running Hosts keep serving', async () => {
  await withBroker({ limits: { hostStartBurst: 1, hostStartsPerMin: 1 }, authCacheMs: 60_000 }, async (_broker, url, config) => {
    assert.equal((await get(url, config, 'sess-a')).status, 200)
    const refused = await get(url, config, 'sess-c')
    assert.equal(refused.status, 429)
    assert.equal(refused.body.error, 'host-start-rate')
    assert.ok(Number(refused.headers.get('retry-after')) >= 1)
    assert.equal((await get(url, config, 'sess-a')).status, 200, 'A keeps its Host')
  })
})

test('audit log: hashed user, session/plugin/provider/trace, never cookies, tokens, email or prompt text', async () => {
  lines.length = 0
  await withBroker({ authCacheMs: 60_000 }, async (_broker, url, config) => {
    const traceparent = '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01'
    const prompt = await call(url, '/api/session/prompt', {
      method: 'POST', session: 'sess-a',
      headers: { origin: config.publicOrigin, traceparent },
      body: { type: 'client-request', rpcId: '1', method: 'session/prompt', payload: { args: { request: { sessionId: 'session-1234abcd', provider: 'mock-openai', text: 'SECRET PROMPT about my portfolio' } } } },
    })
    assert.equal(prompt.status, 404, 'fake Host has no prompt route; the audit still records the call')
    const debug = await get(url, config, 'sess-a', '/api/debug', { 'x-request-id': 'req-42' })
    assert.equal(debug.headers.get('x-request-id'), 'req-42')
    assert.equal(debug.body.headers['x-request-id'], 'req-42', 'X-Request-Id reaches the Host')
    assert.match(debug.body.headers.traceparent, /^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/, 'a traceparent is minted for the Host')
    const traced = await get(url, config, 'sess-a', '/api/debug', { traceparent })
    assert.match(traced.body.headers.traceparent, /^00-4bf92f3577b34da6a3ce929d0e0e4736-(?!00f067aa0ba902b7)[0-9a-f]{16}-01$/, 'same trace, new span')
    assert.ok(api.calls.some(call => call.url === '/me' && /^00-[0-9a-f]{32}-/.test(call.headers.traceparent ?? '')), 'FastAPI /me gets a traceparent')
    assert.ok(api.calls.some(call => call.url === '/internal/dsh/host-tokens' && call.headers.traceparent), 'the token mint gets a traceparent')
  })
  const text = lines.map(line => JSON.stringify(line)).join('\n')
  for (const forbidden of ['sess-a', 'user-a', 'pg_session', 'host.user-a', 'SECRET PROMPT', 'portfolio', 'dsh-auth', SECRET, '@']) {
    assert.ok(!text.includes(forbidden), `audit must not contain ${forbidden}`)
  }
  const rpc = lines.find(line => line.action === 'rpc:session/prompt')
  assert.ok(rpc, text)
  assert.match(rpc.user, /^[0-9a-f]{24}$/)
  assert.equal(rpc.session, 'session-1234abcd')
  assert.equal(rpc.plugin, 'session')
  assert.equal(rpc.provider, 'mock-openai')
  assert.equal(rpc.trace, '4bf92f3577b34da6a3ce929d0e0e4736')
  assert.equal(rpc.status, 404)
  assert.equal(typeof rpc.ms, 'number')
  for (const key of ['ts', 'event', 'action', 'user', 'session', 'plugin', 'provider', 'trace', 'result', 'status', 'ms']) assert.ok(key in rpc, key)
  assert.ok(lines.some(line => line.action === 'http:GET' && line.trace === 'req-42'))
  assert.ok(lines.some(line => line.event === 'host' && line.action === 'host:start' && line.result === 'ok' && line.user === rpc.user))
  assert.deepEqual(identifiersOf('{"a":{"b":{"sessionId":"s-1","providerId":"p"}},"text":"x"}'), { session: 's-1', provider: 'p' })
  assert.deepEqual(identifiersOf('not json'), { session: null, provider: null })
  assert.equal(traceOf({ traceparent: '00-00000000000000000000000000000000-00f067aa0ba902b7-01' }).id.length, 32, 'all-zero trace ids are replaced')
  assert.notEqual(traceOf({ traceparent: 'garbage', 'x-request-id': 'bad id with spaces' }).id, 'bad id with spaces')
})

test('logout: the revoke endpoint closes the user\'s sockets, stops their Host and forgets their identity; others untouched', async () => {
  await withBroker({ authCacheMs: 60_000 }, async (broker, url, config) => {
    const ws = { origin: config.publicOrigin }
    const a = await upgrade(url, '/api/remote.mux', { cookie: 'pg_session=sess-a', ...ws })
    const b = await upgrade(url, '/api/remote.mux', { cookie: 'pg_session=sess-b', ...ws })
    assert.equal(a.status, 101)
    const aClosed = new Promise(resolve => a.socket.once('close', resolve))
    const revokeAs = (headers, body = { user_id: 'user-a' }) => call(url, '/__broker/revoke', { method: 'POST', headers, body })
    assert.equal((await revokeAs({ 'x-puregamma-broker-secret': 'wrong'.padEnd(40, 'x') })).status, 403)
    assert.equal((await revokeAs({})).status, 403)
    assert.equal((await call(url, '/__broker/revoke', { headers: { 'x-puregamma-broker-secret': SECRET } })).status, 405)
    assert.equal((await revokeAs({ 'x-puregamma-broker-secret': SECRET }, {})).status, 400)
    const lookups = api.calls.filter(call => call.url === '/me').length
    assert.equal((await revokeAs({ 'x-puregamma-broker-secret': SECRET })).status, 204)
    await aClosed
    assert.equal(broker.hosts.launched().length, 1, 'A\'s Host stopped, B\'s kept')
    assert.equal(broker.sockets(), 1)
    // A's cached identity is gone: the next request asks FastAPI again.
    await get(url, config, 'sess-a')
    assert.equal(api.calls.filter(call => call.url === '/me').length, lookups + 1)
    b.socket.destroy()
  })
})

test('logout without the notification: open tunnels are re-checked and closed once the session is gone', async () => {
  await withBroker({ authCacheMs: 200 }, async (broker, url, config) => {
    const ws = { origin: config.publicOrigin }
    const a = await upgrade(url, '/api/remote.mux', { cookie: 'pg_session=sess-d', ...ws })
    const b = await upgrade(url, '/api/remote.mux', { cookie: 'pg_session=sess-b', ...ws })
    assert.equal(a.status, 101)
    assert.equal(await broker.revalidateSockets(), 0, 'still signed in')
    delete sessions['sess-d']
    await new Promise(resolve => setTimeout(resolve, 250))
    assert.equal(await broker.revalidateSockets(), 1)
    assert.equal(broker.sockets(), 1, 'only the logged-out tunnel closed')
    assert.ok(lines.some(line => line.event === 'ws' && line.result === 'revalidation-failed'))
    b.socket.destroy()
    a.socket.destroy()
    sessions['sess-d'] = 'user-d'
  })
})
