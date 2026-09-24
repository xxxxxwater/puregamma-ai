import test from 'node:test'
import assert from 'node:assert/strict'
import {
  PIN_PATTERN,
  RELAY_NOT_CONFIGURED,
  isValidPin,
  mutationFailure,
  mutationFromRelay,
  normalizeRelayBase,
  normalizeStatus,
  qrFromResponse,
  qrUnavailable,
  rpcUrl,
} from '../plugins/mobile-access/src/policy.ts'
import { MOBILE_ACCESS_ADMIN_REQUIRED, PocketRelayMobileAccessProvider } from '../plugins/mobile-access/src/index.ts'

/** The provider only needs the Context members it actually uses. */
function fakeContext(services = {}) {
  return { reflect: { provide() {} }, get: name => services[name], effect: () => {} }
}

function provider(config, services) {
  return new PocketRelayMobileAccessProvider(fakeContext(services), config)
}

const adminSession = { pgAuth: { currentUser: async () => ({ role: 'admin' }) } }
const userSession = { pgAuth: { currentUser: async () => ({ role: 'user' }) } }

const statusPayload = (overrides = {}) => ({
  target: 'puregamma-web:3000',
  port: 8787,
  // The relay still publishes a LAN segment; the SaaS view must never carry it.
  lan: { running: true, url: 'http://192.168.1.20:8787', pin: '12345678' },
  public: { running: true, url: 'https://pocket.example.ts.net', pin: '87654321', custom: false, auto_start: true, last_error: null },
  session: { restart_requires_relogin: true },
  ...overrides,
})

// ------------------------------------------------------------------- transport

test('an unconfigured relay is a distinct, explicit state', () => {
  for (const raw of ['', '   ', null, undefined]) assert.equal(normalizeRelayBase(raw), undefined)
  assert.equal(normalizeRelayBase('https://relay.example/'), 'https://relay.example')
  assert.equal(normalizeRelayBase('  https://relay.example//  '), 'https://relay.example')
})

test('relay URLs are built from fixed paths and encoded parameters', () => {
  assert.equal(rpcUrl('https://relay.example', 'status'), 'https://relay.example/rpc/status')
  assert.equal(rpcUrl('https://relay.example', 'qr', { kind: 'public' }), 'https://relay.example/rpc/qr?kind=public')
  assert.equal(rpcUrl('https://relay.example', 'qr', { kind: '', host: 'a b' }), 'https://relay.example/rpc/qr?host=a%20b')
})

test('a PIN is exactly eight digits and nothing else', () => {
  assert.equal(PIN_PATTERN.test('12345678'), true)
  for (const bad of ['1234567', '123456789', '1234567a', ' 12345678', '12345678 ', '', 'abcdefgh']) {
    assert.equal(isValidPin(bad), false, JSON.stringify(bad))
  }
})

// ---------------------------------------------------------- the LAN invariant

test('the private LAN segment never reaches a client, whatever the relay publishes', () => {
  const view = normalizeStatus(statusPayload(), { isAdmin: true, observedAtMs: 0 })
  assert.equal(view.available, true)
  assert.equal('lan' in view, false)
  // Belt and braces: the raw LAN address must not survive anywhere in the view.
  assert.doesNotMatch(JSON.stringify(view), /192\.168\./)
  assert.deepEqual(Object.keys(view.publicTunnel).sort(), ['autoStart', 'custom', 'lastError', 'pin', 'running', 'url'])
})

test('the admin flag is the host decision and is echoed, never inferred from the relay', () => {
  assert.equal(normalizeStatus(statusPayload(), { isAdmin: false, observedAtMs: 0 }).isAdmin, false)
  assert.equal(normalizeStatus(statusPayload({ admin: true }), { isAdmin: false, observedAtMs: 0 }).isAdmin, false)
  assert.equal(normalizeStatus(statusPayload(), { isAdmin: true, observedAtMs: 0 }).isAdmin, true)
})

// ------------------------------------------------------------------ fail closed

test('an unexpected or empty status payload is unavailable, never a stopped tunnel with a blank PIN', () => {
  for (const payload of [null, 'text', 42, [], undefined]) {
    const view = normalizeStatus(payload, { isAdmin: false, observedAtMs: 0 })
    assert.equal(view.available, false, JSON.stringify(payload))
    assert.equal('publicTunnel' in view, false)
    assert.ok(String(view.reason).length > 0)
  }
})

test('a relay payload missing the public segment does not fabricate a running tunnel', () => {
  const view = normalizeStatus({ target: 'web:3000', port: 1 }, { isAdmin: true, observedAtMs: 0 })
  assert.equal(view.available, true)
  assert.equal(view.publicTunnel.running, false)
  assert.equal(view.publicTunnel.url, null)
  assert.equal(view.publicTunnel.pin, null)
})

test('a QR response is only accepted when it really is a non-empty PNG', () => {
  const png = new Uint8Array([137, 80, 78, 71])
  assert.equal(qrFromResponse('image/png', png).available, true)
  assert.equal(qrFromResponse('image/png; charset=binary', png).available, true)
  assert.equal(qrFromResponse('application/json', png).available, false)
  assert.equal(qrFromResponse(null, png).available, false)
  assert.equal(qrFromResponse('image/png', new Uint8Array()).available, false)
  assert.equal(qrUnavailable('no URL available').available, false)
})

test('a relay error body never becomes a success-shaped mutation', () => {
  const failed = mutationFailure('pocket relay tunnel/start returned HTTP 502', 0)
  assert.equal(failed.ok, false)
  assert.equal('running' in failed, false)
  assert.equal('pin' in failed, false)
  const response = mutationFromRelay({ detail: 'no URL available' }, 0)
  assert.equal(response.ok, true)
  assert.equal('running' in response, false, 'a missing field must stay missing, not default to false')
})

// ------------------------------------------------------- server-side authorization

test('without an installed auth capability only reading is possible', async () => {
  const nav = provider({ relayUrl: 'http://127.0.0.1:1' }, {})
  assert.equal((await nav.status()).isAdmin, false)
  for (const result of [await nav.startTunnel(), await nav.stopTunnel(), await nav.rotatePin('public'), await nav.setPin('public', '12345678')]) {
    assert.equal(result.ok, false)
    assert.equal(result.reason, MOBILE_ACCESS_ADMIN_REQUIRED)
  }
})

test('a signed-in non-admin cannot change tunnel or PIN state', async () => {
  const nav = provider({ relayUrl: 'http://127.0.0.1:1' }, userSession)
  const status = await nav.status()
  assert.equal(status.isAdmin, false)
  for (const result of [await nav.startTunnel(), await nav.stopTunnel(), await nav.rotatePin('public'), await nav.setPin('public', '12345678')]) {
    assert.equal(result.ok, false)
    assert.equal(result.reason, MOBILE_ACCESS_ADMIN_REQUIRED)
  }
})

test('authorization is decided before input validation, so refusal text leaks nothing', async () => {
  const nav = provider({ relayUrl: 'http://127.0.0.1:1' }, userSession)
  // A malformed PIN from a non-admin must report the authorization refusal, not
  // "PIN must be exactly eight digits", which would confirm the format.
  assert.equal((await nav.setPin('public', 'nope')).reason, MOBILE_ACCESS_ADMIN_REQUIRED)
  assert.equal((await nav.rotatePin('lan')).reason, MOBILE_ACCESS_ADMIN_REQUIRED)
})

test('an admin still gets an explicit refusal when the relay is not configured', async () => {
  const nav = provider({ relayUrl: '' }, adminSession)
  const status = await nav.status()
  assert.equal(status.available, false)
  assert.equal(status.reason, RELAY_NOT_CONFIGURED)
  assert.equal('publicTunnel' in status, false)
  assert.equal(status.isAdmin, true, 'the admin flag is still reported so the UI can explain the outage')
  assert.equal((await nav.startTunnel()).reason, RELAY_NOT_CONFIGURED)
  assert.equal((await nav.qr()).reason, RELAY_NOT_CONFIGURED)
})

test('a failing session is treated as a non-admin rather than inherited from the caller', async () => {
  const nav = provider({ relayUrl: 'http://127.0.0.1:1' }, { pgAuth: { currentUser: async () => { throw new Error('no session') } } })
  assert.equal((await nav.status()).isAdmin, false)
  assert.equal((await nav.startTunnel()).reason, MOBILE_ACCESS_ADMIN_REQUIRED)
})

test('an unreachable relay is reported as unreachable for an admin', async () => {
  const nav = provider({ relayUrl: 'http://127.0.0.1:1', requestTimeoutMs: 200 }, adminSession)
  const status = await nav.status()
  assert.equal(status.available, false)
  assert.match(String(status.reason), /unreachable/)
  assert.equal((await nav.startTunnel()).ok, false)
})
