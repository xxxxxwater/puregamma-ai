import assert from 'node:assert/strict'
import test from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { NavToolView, readNavPresentation } from '../plugins/ui-portfolio/src/client/index.ts'
import { ResearchToolView, readResearchPresentation } from '../plugins/ui-research/src/client/index.ts'
import { ToolView as OptionsToolView } from '../plugins/ui-options/src/client/index.ts'
import { ToolView as BacktestToolView } from '../plugins/ui-backtest/src/client/index.ts'
import { ToolView as MemoryToolView, readPresentation as readMemoryPresentation } from '../plugins/ui-memory/src/client/index.ts'

// The domain tool views render only the tool result's presentation `meta`.
// These pin their honesty rules: no zero for a missing NAV, stale and degraded
// are said out loud, and anything that is not the v1 DTO renders nothing.

const t = key => key
const result = (meta, isError = false) => ({ kind: 'tool-result', seq: 1, time: 0, callId: 'c', call: null, callTime: null, content: [], isError, meta, subCalls: [] })
const running = { callId: 'c', name: 'portfolio_nav', argsRaw: '{}', turn: 1, step: 1, time: 0, subCalls: [] }
const nav = overrides => ({ schema: 'puregamma.portfolio.nav/v1', available: true, stale: false, currency: 'USD', nav: '1234567.8912', cash: '45000.00', observedAt: '2026-10-28T08:00:00Z', priceObservedAt: '2026-10-28T07:59:30Z', calculationVersion: '3', positions: null, reason: null, ...overrides })
const render = (View, block) => renderToStaticMarkup(createElement(View, { block, t, callId: 'c', toolName: 'x', openFile: () => {}, loadImage: async () => '' }))

test('a live NAV states amount, currency, times and calculation, with every decimal kept', () => {
  const html = render(NavToolView, result(nav({})))
  assert.match(html, /data-state="live"/)
  assert.match(html, /1,234,567\.8912 USD/)
  assert.match(html, /observed: 2026-10-28T08:00:00Z/)
  assert.match(html, /prices: 2026-10-28T07:59:30Z/)
  assert.match(html, /cash: 45,000\.00 USD/)
})

test('a stale NAV is labelled as not current', () => {
  const html = render(NavToolView, result(nav({ stale: true })))
  assert.match(html, /data-state="stale"/)
  assert.match(html, /stale/)
})

test('a missing NAV is unavailable with the server reason, never zero', () => {
  const html = render(NavToolView, result(nav({ available: false, nav: null, cash: null, reason: 'no connected portfolio snapshot' })))
  assert.match(html, /data-state="unavailable"/)
  assert.match(html, /no connected portfolio snapshot/)
  assert.doesNotMatch(html, />0(\.0+)? USD</)
})

test('running, failed and malformed results never show a figure', () => {
  assert.match(render(NavToolView, running), /reading/)
  assert.match(render(NavToolView, result(nav({}), true)), /failed/)
  assert.match(render(NavToolView, result({ schema: 'something-else', nav: '1' })), /noMeta/)
  assert.equal(readNavPresentation({ schema: 'puregamma.portfolio.nav/v1' }), null)
})

test('research views state provenance and degradation, not content', () => {
  const meta = { schema: 'puregamma.research.document/v1', kind: 'overnight', asOf: '2026-10-28T06:00:00Z', observedAt: '2026-10-28T08:00:00Z', degraded: true, source: 'compatibility:research-api', sections: ['what_happened', 7, 'risks'] }
  const html = render(ResearchToolView, result(meta))
  assert.match(html, /data-degraded="true"/)
  assert.match(html, /overnight/)
  assert.match(html, /asOf: 2026-10-28T06:00:00Z/)
  assert.match(html, /source: compatibility:research-api/)
  assert.match(html, /what_happened, risks/)
  assert.match(html, /degraded/)
  assert.deepEqual(readResearchPresentation({ ...meta, kind: 'not-a-kind' }), null)
})

test('options views always say research only, and flag a degraded or unavailable provider', () => {
  const meta = { schema: 'puregamma.options.document/v1', kind: 'chain', underlying: 'BTC', provider: 'deribit', observedAt: '2026-10-28T08:00:00Z', state: 'degraded', executionEnabled: false, source: 'compatibility:options-api', size: 120 }
  const html = render(OptionsToolView, result(meta))
  assert.match(html, /data-state="degraded"/)
  assert.match(html, /chain · BTC/)
  assert.match(html, /rows: 120/)
  assert.match(html, /researchOnly/)
  assert.match(html, /degraded/)
  assert.match(render(OptionsToolView, result({ ...meta, state: 'unavailable', size: null })), /unavailable/)
})

test('backtest views copy reported metrics and label the run as simulated', () => {
  const meta = { schema: 'puregamma.backtest.document/v1', kind: 'run', observedAt: '2026-10-28T08:00:00Z', source: 'compatibility:backtest-api', runId: 'bt-42', status: 'completed', metrics: [{ name: 'sharpe', value: 1.83 }, { name: 'max_drawdown', value: -0.112 }, { name: 'bad', value: 'x' }] }
  const html = render(BacktestToolView, result(meta))
  assert.match(html, /run: bt-42 · status: completed/)
  assert.match(html, /sharpe 1\.83 · max_drawdown -0\.112/)
  assert.doesNotMatch(html, /bad x/)
  assert.match(html, /simulated/)
})

test('memory views show counts only, never contents', () => {
  const meta = { schema: 'puregamma.memory.document/v1', kind: 'items', observedAt: '2026-10-28T08:00:00Z', source: 'compatibility:memory-api', count: 3, items: [{ content_preview: 'secret note' }] }
  const html = render(MemoryToolView, result(meta))
  assert.match(html, /count: 3/)
  assert.match(html, /private/)
  assert.doesNotMatch(html, /secret note/)
  assert.equal(readMemoryPresentation({ ...meta, kind: 'bogus' }), null)
})
