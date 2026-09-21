import test from 'node:test'
import assert from 'node:assert/strict'
import { canonicalPositiveDecimal, decimalWithin, evaluateExecutionEligibility } from '../plugins/trading-mandates/src/policy.ts'

const now = '2026-09-21T00:00:00.000Z'
const mandate = {
  id: 'm-1', revision: '7', state: 'active', accountId: 'acct-1', venue: 'BINANCE_PM',
  instruments: ['BTCUSDT'], sides: ['buy'], maxOrderQuantity: '0.50000001',
  maxOrderNotional: '100000.00000001', expiresAt: '2026-09-22T00:00:00.000Z',
}
const approval = {
  id: 'a-1', mandateId: 'm-1', mandateRevision: '7', state: 'approved',
  requestedBy: 'strategy-1', approvedBy: 'human-2', clientOrderId: 'cid-1',
  intentHash: 'sha256:abc', expiresAt: '2026-09-21T01:00:00.000Z',
}
const evidence = {
  origin: 'server-risk', observedAt: now, orderNotional: '100000.00000001',
  killSwitchEngaged: false, reconciliationHealthy: true, ownershipVerified: true,
  brokerHealthy: true, reduceOnlyVerified: true, unresolvedIntent: false,
}
const valid = {
  mandate, approval, evidence, accountId: 'acct-1', venue: 'BINANCE_PM',
  instrument: 'BTCUSDT', side: 'buy', quantity: '0.50000001', reduceOnly: false,
  requester: 'strategy-1', clientOrderId: 'cid-1', intentHash: 'sha256:abc', now,
}
const evaluate = (patch = {}) => evaluateExecutionEligibility({ ...valid, ...patch })
const blocked = (result, code) => {
  assert.equal(result.eligibleForReservation, false)
  assert.ok(result.blockers.includes(code), `Expected blocker ${code}; received ${result.blockers.join(',')}`)
}

test('even a clean result is reservation eligibility, not an order submission or approval token', () => {
  assert.deepEqual(evaluate(), { eligibleForReservation: true, blockers: [], mandateId: 'm-1', approvalId: 'a-1' })
  assert.equal('authorizationToken' in evaluate(), false)
})
test('missing mandate, approval, risk or clock each fails closed', () => {
  blocked(evaluate({ mandate: undefined }), 'mandate_missing')
  blocked(evaluate({ approval: undefined }), 'independent_approval_missing')
  blocked(evaluate({ evidence: undefined }), 'trusted_risk_missing')
  blocked(evaluate({ now: 'invalid' }), 'invalid_clock')
})
test('mandate state, scope, expiry and revision are mandatory', () => {
  for (const state of ['paused', 'revoked', 'expired']) blocked(evaluate({ mandate: { ...mandate, state } }), 'mandate_inactive')
  blocked(evaluate({ venue: 'HYPERLIQUID' }), 'mandate_scope_mismatch')
  blocked(evaluate({ instrument: 'ETHUSDT' }), 'mandate_scope_mismatch')
  blocked(evaluate({ side: 'sell' }), 'mandate_scope_mismatch')
  blocked(evaluate({ now: mandate.expiresAt }), 'mandate_expired_or_invalid')
  blocked(evaluate({ mandate: { ...mandate, revision: '8' } }), 'approval_binding_mismatch')
})
test('independent approval binds one exact request and cannot be consumed or self-approved', () => {
  blocked(evaluate({ approval: { ...approval, approvedBy: 'strategy-1' } }), 'approval_not_independent')
  blocked(evaluate({ approval: { ...approval, state: 'consumed' } }), 'independent_approval_inactive')
  blocked(evaluate({ approval: { ...approval, state: 'pending' } }), 'independent_approval_inactive')
  blocked(evaluate({ clientOrderId: 'cid-2' }), 'approval_binding_mismatch')
  blocked(evaluate({ intentHash: 'sha256:changed' }), 'approval_binding_mismatch')
  blocked(evaluate({ now: approval.expiresAt }), 'approval_expired_or_invalid')
})
test('risk freshness, kill switch, venue ownership, unresolved submissions and reduce-only all gate exposure', () => {
  blocked(evaluate({ evidence: { ...evidence, observedAt: '2026-09-20T23:59:54.000Z' } }), 'risk_evidence_stale')
  blocked(evaluate({ evidence: { ...evidence, observedAt: '2026-09-21T00:00:02.000Z' } }), 'risk_evidence_stale')
  blocked(evaluate({ evidence: { ...evidence, killSwitchEngaged: true } }), 'execution_safety_blocked')
  blocked(evaluate({ evidence: { ...evidence, reconciliationHealthy: false } }), 'execution_safety_blocked')
  blocked(evaluate({ evidence: { ...evidence, ownershipVerified: false } }), 'execution_safety_blocked')
  blocked(evaluate({ evidence: { ...evidence, brokerHealthy: false } }), 'execution_safety_blocked')
  blocked(evaluate({ evidence: { ...evidence, unresolvedIntent: true } }), 'execution_safety_blocked')
  blocked(evaluate({ reduceOnly: true, evidence: { ...evidence, reduceOnlyVerified: false } }), 'reduce_only_unverified')
})
test('positive decimal comparisons preserve sub-satoshi precision and never use float coercion', () => {
  assert.equal(canonicalPositiveDecimal('0.0000000100'), '0.00000001')
  assert.equal(decimalWithin('100000.00000001', '100000.00000001'), true)
  assert.equal(decimalWithin('100000.00000002', '100000.00000001'), false)
  assert.equal(decimalWithin('0.500000010', '0.50000001'), true)
  for (const bad of ['1e-8', '-1', '0', '0.0000', 'NaN', 'Infinity', '01', '1.']) assert.equal(canonicalPositiveDecimal(bad), undefined)
  blocked(evaluate({ quantity: '0.50000002' }), 'quantity_exceeds_mandate')
  blocked(evaluate({ evidence: { ...evidence, orderNotional: '100000.00000002' } }), 'notional_exceeds_mandate')
  blocked(evaluate({ evidence: { ...evidence, orderNotional: '1e5' } }), 'notional_exceeds_mandate')
})
