import test from 'node:test'
import assert from 'node:assert/strict'
import { parsePgTsyHealth } from '../plugins/pg-tsy-runtime-http/src/health-contract.ts'

const health = {
  process_healthy: true, ready: true, mode: 'shadow', lease_healthy: true,
  feeds_total: 2, feeds_connected: 2, events_total: 12,
  policy_decisions_total: 9, open_orders: 1, orders_journaled_total: 3,
  blocking_gates: [], last_error: null,
}
const parse = (data = health, path = '/healthz', status = 200) =>
  parsePgTsyHealth(data, path, status, 'http://127.0.0.1:8080')

test('Rust health ABI yields real observed counters, not surrogate balances or positions', () => {
  const result = parse()
  assert.equal(result.ready, true)
  assert.equal(result.mode, 'shadow')
  assert.equal(result.eventsTotal, 12)
  assert.equal(result.openOrders, 1)
  assert.equal(result.source, 'http://127.0.0.1:8080')
  assert.deepEqual(result.blockingGates, [])
  assert.equal('positions' in result, false)
  assert.equal('liveTradingEnabled' in result, false)
})
test('booting/unready is not invented as healthy readiness', () => {
  const booting = { ...health, ready: false, lease_healthy: false, blocking_gates: ['RuntimeLeaseAcquired'] }
  const result = parse(booting, '/readyz', 503)
  assert.equal(result.ready, false)
  assert.equal(result.leaseHealthy, false)
  assert.deepEqual(result.blockingGates, ['RuntimeLeaseAcquired'])
})
test('unhealthy process is explicit, not silently normalized into a success', () => {
  const down = { ...health, process_healthy: false, ready: false, lease_healthy: false, blocking_gates: ['DatabaseReachable'] }
  assert.equal(parse(down, '/healthz', 503).processHealthy, false)
  assert.throws(() => parse(down, '/healthz', 200), /contradicts/)
})
test('HTTP error/status mismatch and invalid body fail closed', () => {
  assert.throws(() => parse(health, '/healthz', 503), /contradicts/)
  assert.throws(() => parse(health, '/readyz', 503), /contradicts/)
  assert.throws(() => parse(health, '/healthz', 404), /contradicts/)
  for (const invalid of [null, [], 'ok', 0]) assert.throws(() => parse(invalid), /object/)
})
test('missing counters and booleans cannot masquerade as zero or false', () => {
  for (const field of ['feeds_total', 'feeds_connected', 'events_total', 'policy_decisions_total', 'open_orders', 'orders_journaled_total']) {
    const payload = { ...health }
    delete payload[field]
    assert.throws(() => parse(payload), /missing or unsafe counter/)
  }
  for (const field of ['process_healthy', 'ready', 'lease_healthy']) {
    const payload = { ...health }
    delete payload[field]
    assert.throws(() => parse(payload), /missing boolean/)
  }
  assert.throws(() => parse({ ...health, blocking_gates: undefined }), /invalid blocking_gates/)
})
test('unsafe Rust u64 counters and contradictory readiness are rejected', () => {
  for (const invalid of [NaN, Infinity, -1, 0.2, Number.MAX_SAFE_INTEGER + 1, '12', null]) {
    assert.throws(() => parse({ ...health, events_total: invalid }), /unsafe counter/)
  }
  assert.throws(() => parse({ ...health, feeds_connected: 3 }), /inconsistent readiness/)
  assert.throws(() => parse({ ...health, lease_healthy: false }), /inconsistent readiness/)
  assert.throws(() => parse({ ...health, blocking_gates: ['unreconciled'] }), /inconsistent readiness/)
  assert.throws(() => parse({ ...health, mode: 'live-but-not-really' }), /unknown execution mode/)
  assert.throws(() => parse({ ...health, blocking_gates: [null] }), /invalid blocking_gates/)
  assert.throws(() => parse({ ...health, last_error: {} }), /invalid last_error/)
})
