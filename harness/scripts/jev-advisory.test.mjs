import test from 'node:test'
import assert from 'node:assert/strict'
import { compareJevWithSignal, validateJevObservation } from '../plugins/pg-tsy-runtime/src/jev.ts'

const base = 1_800_000_000_000_000_000n
const source = base.toString()
const received = (base + 100n).toString()
const now = (base + 200n).toString()
const expires = (base + 1_000_000_000n).toString()
const observation = {
  instrument: 'BINANCE_PM:BTCUSDC', model: 'jev-1.13.0',
  source_event_ns: source, received_ns: received, expires_ns: expires,
  choice: 'up', probabilities: { up: 0.7, down: 0.2, neutral: 0.1 },
  provider_confidence: 0.8, input_tokens: 10, output_tokens: 2,
}
const signal = {
  venue: 'BINANCE_PM', instrument: 'BTCUSDC', score: 0.6,
  source_event_ns: source, created_at_ns: (base + 150n).toString(),
  expires_at_ns: (base + 1_500_000_000n).toString(),
}

test('canonical nanosecond strings retain precision beyond Number.MAX_SAFE_INTEGER', () => {
  assert.equal(validateJevObservation(observation, now)?.source_event_ns, source)
  assert.equal(validateJevObservation({ ...observation, source_event_ns: Number(source) }, now), undefined)
  assert.equal(validateJevObservation({ ...observation, source_event_ns: `0${source}` }, now), undefined)
  assert.equal(validateJevObservation({ ...observation, received_ns: Number(received) }, now), undefined)
})

test('advice can agree with a matching existing signal, never authorize an order', () => {
  assert.equal(compareJevWithSignal(observation, signal, 'increase', now), 'advice-agrees')
  assert.equal(compareJevWithSignal(observation, { ...signal, score: -1 }, 'increase', now), 'hold-new-exposure')
  assert.equal(compareJevWithSignal({ ...observation, choice: 'neutral', probabilities: { up: 0.2, down: 0.2, neutral: 0.6 } }, signal, 'increase', now), 'hold-new-exposure')
  assert.equal(compareJevWithSignal(observation, { ...signal, source_event_ns: (base + 1n).toString() }, 'increase', now), 'hold-new-exposure')
  assert.equal(compareJevWithSignal(observation, { ...signal, venue: 'HYPERLIQUID' }, 'increase', now), 'hold-new-exposure')
})

test('missing, stale, future, bad probability or wrong model fails closed only for entries', () => {
  const cases = [
    undefined,
    { ...observation, model: 'jev-latest' },
    { ...observation, instrument: 'BINANCE_PM:BTCUSDT' },
    { ...observation, received_ns: (base + 500n).toString() },
    { ...observation, expires_ns: now },
    { ...observation, expires_ns: (base + 5_000_000_001n).toString() },
    { ...observation, probabilities: { up: 0.3, down: 0.3, neutral: 0.3 } },
    { ...observation, probabilities: { up: 0.7, down: 0.2, neutral: 0.1, other: 0 } },
    { ...observation, provider_confidence: Number.NaN },
    { ...observation, input_tokens: Number.MAX_SAFE_INTEGER + 1 },
  ]
  for (const candidate of cases) {
    assert.equal(validateJevObservation(candidate, now), undefined)
    assert.equal(compareJevWithSignal(candidate, signal, 'increase', now), 'hold-new-exposure')
    assert.equal(compareJevWithSignal(candidate, signal, 'reduce-only', now), 'reduction-independent')
  }
})

test('expired or mismatched deterministic signal is held; reduce-only is never model-gated', () => {
  assert.equal(compareJevWithSignal(observation, { ...signal, expires_at_ns: now }, 'increase', now), 'hold-new-exposure')
  assert.equal(compareJevWithSignal(observation, { ...signal, created_at_ns: (base - 1n).toString() }, 'increase', now), 'hold-new-exposure')
  assert.equal(compareJevWithSignal(observation, signal, 'increase', expires), 'hold-new-exposure')
  assert.equal(compareJevWithSignal(undefined, signal, 'reduce-only', expires), 'reduction-independent')
})
