import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { CANDIDATE_GATES, validateRetirement } from './retirement-gate.mjs'

// The retirement gate's rules on synthetic ledgers, plus the real evidence file.

const rows = (prefix, count, extra = '') => Array.from({ length: count }, (_, index) => `  { surface: '${prefix}${index}.py', target: 'market-data' },`).join('\n') + extra
const apiMap = rows('apps/api/routers/r', 38, "\n  { surface: 'apps/api/routers/market.py', target: 'market-data' },")
const webMap = rows('apps/web/app/p', 83).replaceAll('target:', 'owner:')
const everything = () => true
const gates = (status = 'met') => Object.fromEntries(CANDIDATE_GATES.map(gate => [gate, { status, evidence: 'scripts/x.test.mjs', next: 'owner: W4' }]))
const run = (certificate, exists = everything) => validateRetirement({ webMap, apiMap, certificate: { schemaVersion: 1, retired: {}, ...certificate }, exists })
const certificate = { owner: 'market-data', replacementPlugin: '@puregamma/dsh-market-data', identityBinding: 'per-user token', readWritePermissions: 'read only', observableStates: 'stale/unavailable', bilingualUi: 'English and Chinese copy', lifecycleCleanup: 'cordis dispose', streamAndBinaryParity: 'n/a: none', e2eArtifactUrl: 'https://ci.example/run/1', rollbackProcedure: 'restore router', reviewedBy: 'reviewer@example', verifiedAt: '2026-10-29T12:00:00Z', integratedCommit: 'a'.repeat(40), imageDigest: `sha256:${'b'.repeat(64)}` }

test('an empty evidence file passes while every legacy file exists', () => {
  assert.deepEqual(run({}).errors, [])
})

test('deleting a legacy route without a certificate fails; a complete certificate allows it', () => {
  const gone = surface => surface !== 'apps/api/routers/market.py'
  assert.match(run({}, gone).errors.join('\n'), /deleted without verified retirement certificate: apps\/api\/routers\/market\.py/)
  assert.deepEqual(run({ retired: { 'apps/api/routers/market.py': certificate } }, gone).errors, [])
  for (const [field, broken] of [['imageDigest', 'latest'], ['e2eArtifactUrl', 'http://insecure'], ['integratedCommit', 'abc'], ['reviewedBy', '']]) {
    assert.ok(run({ retired: { 'apps/api/routers/market.py': { ...certificate, [field]: broken } } }, gone).errors.length > 0, field)
  }
})

test('a candidate records progress but never authorizes a deletion', () => {
  const candidates = { 'apps/api/routers/market.py': { owner: 'market-data', gates: gates('met') } }
  const ok = run({ candidates })
  assert.deepEqual(ok.errors, [])
  assert.deepEqual(ok.candidates, [{ surface: 'apps/api/routers/market.py', met: CANDIDATE_GATES.length, total: CANDIDATE_GATES.length }])
  const gone = surface => surface !== 'apps/api/routers/market.py'
  const errors = run({ candidates }, gone).errors.join('\n')
  assert.match(errors, /candidate is not a certificate; its legacy file must still exist/)
  assert.match(errors, /deleted without verified retirement certificate/)
  assert.match(run({ candidates, retired: { 'apps/api/routers/market.py': certificate } }).errors.join('\n'), /both a retirement candidate and retired/)
})

test('every gate is accounted for, with evidence when claimed and a next step when not met', () => {
  const surface = 'apps/api/routers/market.py'
  const missingGate = gates('met'); delete missingGate.observability
  assert.match(run({ candidates: { [surface]: { owner: 'market-data', gates: missingGate } } }).errors.join('\n'), /does not account for gate observability/)
  const noEvidence = { ...gates('met'), parityTests: { status: 'partial', evidence: '', next: 'W4' } }
  assert.match(run({ candidates: { [surface]: { owner: 'market-data', gates: noEvidence } } }).errors.join('\n'), /parityTests is partial without evidence/)
  const noNext = { ...gates('met'), humanReview: { status: 'missing' } }
  assert.match(run({ candidates: { [surface]: { owner: 'market-data', gates: noNext } } }).errors.join('\n'), /humanReview is missing without a next step/)
  assert.match(run({ candidates: { [surface]: { owner: 'portfolio', gates: gates() } } }).errors.join('\n'), /candidate owner mismatch/)
  assert.match(run({ candidates: { [surface]: { owner: 'market-data', gates: { ...gates(), vibes: { status: 'met', evidence: 'trust me please' } } } } }).errors.join('\n'), /unknown gate vibes/)
  assert.match(run({ candidates: { [surface]: { owner: 'market-data', gates: { ...gates(), invariants: { status: 'done', evidence: 'x'.repeat(10) } } } } }).errors.join('\n'), /invalid status done/)
})

test('the committed evidence retires nothing yet and tracks Market Data and Portfolio as candidates', () => {
  const evidence = JSON.parse(readFileSync(new URL('../retirement-evidence.json', import.meta.url), 'utf8'))
  assert.deepEqual(evidence.retired, {}, 'no surface has deployment, E2E artifact and human review evidence yet')
  for (const surface of ['apps/api/routers/market.py', 'apps/api/routers/portfolio.py']) {
    const candidate = evidence.candidates[surface]
    assert.ok(candidate, surface)
    for (const gate of ['e2eArtifact', 'deploymentImage', 'humanReview']) assert.equal(candidate.gates[gate].status, 'missing', `${surface} ${gate} cannot be claimed from a workstation`)
  }
})
