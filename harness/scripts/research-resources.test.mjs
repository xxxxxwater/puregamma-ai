import assert from 'node:assert/strict'
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import PureGammaClientGateway, { readFailureReason } from '../packages/client-gateway/src/index.ts'
import {
  backtestArtifactView, researchArtifactsView, researchRunView, researchRunsView, MAX_ARTIFACT_MARKDOWN,
} from '../packages/client-gateway/src/research-views.ts'
import { createResearchRunsClient, parseServerSentEvents } from '../plugins/research-legacy-api/src/runs.ts'
import {
  BacktestArtifactBody, IndexBody, PROTOCOL, ResearchArtifactBody, ResearchRunBody, followResearchRun, pollResource, resourceAddress, resourceId,
} from '../plugins/ui-research-resources/src/client/index.ts'

// Research/backtest resource views: the Host projection forwards named fields
// only, the browser loop recovers from lost reads without erasing what it
// knew, and every view says loading/failed/unavailable/stale out loud instead
// of showing a zero or a blank.

const doc = (payload, source = 'compatibility:research-runs-api') => ({ observedAt: '2026-10-29T08:00:00Z', source, payload })
const run = overrides => ({ id: 'run-1', name: 'BTC funding', status: 'running', verification: null, created_at: '2026-10-29T07:00:00Z', updated_at: '2026-10-29T07:59:00Z', evidence_count: 4, citation_count: 2, credits_used: null, is_degraded: false, error_message: null, summary: null, disclaimer: '仅供研究参考', data_sources: ['news'], ...overrides })

test('a research run projection copies named fields and leaves unreported values undefined, never zero', () => {
  const view = researchRunView(doc({ run: run({ credits_used: undefined, evidence_count: 'x', secret_token: 'abc', prompt: 'private prompt' }) }))
  assert.equal(view.available, true)
  assert.equal(view.terminal, false)
  assert.equal(view.run.creditsUsed, undefined)
  assert.equal(view.run.evidenceCount, undefined)
  assert.equal(view.run.citationCount, 2)
  assert.equal(JSON.stringify(view).includes('abc'), false, 'unknown keys never cross to the browser')
  assert.equal(JSON.stringify(view).includes('private prompt'), false)
  for (const status of ['completed', 'degraded', 'failed', 'canceled', 'timed_out']) assert.equal(researchRunView(doc({ run: run({ status }) })).terminal, true, status)
  assert.equal(researchRunView(doc({ run: run({ status: 'queued' }) })).terminal, false)
  const missing = researchRunView(doc({}))
  assert.equal(missing.available, false)
  assert.match(missing.reason, /no run/)
})

test('research artifacts forward report text capped, and only plain http(s) citation links', () => {
  const long = 'x'.repeat(MAX_ARTIFACT_MARKDOWN + 10)
  const view = researchArtifactsView('run-1', doc({ artifacts: [{ id: 'a1', type: 'report', title: 'Report', status: 'ready', markdown: long, url: null, storage_path: '/srv/x' }, { title: 'no id' }] }), doc({ evidence: [
    { id: 'e1', title: 'Funding spikes', source: 'coindesk', url: 'https://example.com/a' },
    { id: 'e2', title: 'Bad scheme', url: 'javascript:alert(1)' },
    { id: 'e3', title: 'Embedded credential', url: 'https://user:pass@example.com/' },
  ] }))
  assert.equal(view.artifacts.length, 1)
  assert.equal(view.artifacts[0].markdown.length, MAX_ARTIFACT_MARKDOWN)
  assert.equal(view.artifacts[0].markdownTruncated, true)
  assert.equal(JSON.stringify(view).includes('/srv/x'), false)
  assert.deepEqual(view.evidence.map(item => item.url), ['https://example.com/a', undefined, undefined])
  assert.equal(view.evidenceAvailable, true)
  const noEvidence = researchArtifactsView('run-1', doc({ artifacts: [] }), undefined)
  assert.equal(noEvidence.evidenceAvailable, false, 'a failed evidence read is not "no evidence"')
})

test('backtest artifacts copy reported metrics verbatim and never forward the storage path', () => {
  const view = backtestArtifactView(doc({ run: { id: 'bt-1', status: 'completed', engine: 'vectorbt', strategy_name: 'Momentum', asset: 'BTC', window: { start: '2026-09-01', end: '2026-10-01' }, performance: { sharpe: 1.83, max_drawdown: -0.112, label: 'n/a', nan: null }, artifacts: [{ id: 'f1', artifact_type: 'report', format: 'json', relative_path: 'user/bt-1/report.json', size_bytes: 2048, checksum: 'abc123' }], error: {} } }, 'compatibility:backtest-api'))
  assert.deepEqual(view.metrics, [{ name: 'sharpe', value: 1.83 }, { name: 'max_drawdown', value: -0.112 }])
  assert.equal(view.artifacts[0].sizeBytes, 2048)
  assert.equal(JSON.stringify(view).includes('relative_path'), false)
  assert.equal(JSON.stringify(view).includes('user/bt-1'), false)
  const bare = backtestArtifactView(doc({ run: { id: 'bt-2', status: 'running' } }))
  assert.deepEqual(bare.metrics, [])
  assert.equal(bare.run.completedAt, undefined)
  assert.equal(researchRunsView(doc({ runs: [run({}), { nope: 1 }] })).runs.length, 1)
})

test('failure reasons are classified by status; provider text (URLs, bodies) never reaches the browser', () => {
  const error = new Error('research runs compatibility API returned HTTP 404 for /api/research/runs/x: {"detail":"internal host 10.0.0.5"}')
  assert.equal(readFailureReason(error, 'research run'), 'research run was not found')
  assert.equal(readFailureReason(new Error('HTTP 503'), 'research run'), 'research run is unavailable: the service returned HTTP 503')
  assert.equal(readFailureReason(new Error('HTTP 401'), 'research run'), 'research run is not available to this account')
  assert.match(readFailureReason(new Error('PureGamma Harness research runs provider requires bearer token in authTokenFile /x'), 'research run'), /no signed-in user/)
  assert.equal(readFailureReason(new Error('ECONNREFUSED 127.0.0.1:8000'), 'research run'), 'research run is currently unavailable')
})

function gatewayWith(services) {
  const gateway = Object.create(PureGammaClientGateway.prototype)
  Object.defineProperty(gateway, 'ctx', { value: { get: name => services[name] } })
  return gateway
}

test('researchRunWait follows SSE until the status changes, and falls back to a plain read when the stream fails', async () => {
  const reads = []
  const make = events => ({
    run: async id => { reads.push(id); return doc({ run: run({ id, status: 'completed' }) }) },
    events: events,
  })
  const seen = []
  const gateway = gatewayWith({ pgResearchRuns: make(async function* () {
    yield { event: 'run.state', data: { status: 'running' } }
    seen.push('same')
    yield { event: 'run.state', data: { status: 'completed' } }
    seen.push('after-change')
  }) })
  const view = await gateway.researchRunWait('run-1', 'running')
  assert.deepEqual(seen, ['same'], 'stops at the first changed status')
  assert.equal(view.run.status, 'completed')
  assert.equal(view.terminal, true)
  const broken = gatewayWith({ pgResearchRuns: make(async function* () { throw new Error('HTTP 502') }) })
  assert.equal((await broken.researchRunWait('run-2', 'running')).run.status, 'completed')
  assert.deepEqual(reads, ['run-1', 'run-2'])
  assert.equal((await gatewayWith({}).researchRunWait('run-1', 'running')).available, false)
  assert.match((await gateway.researchRunWait('../etc', 'running')).reason, /invalid/)
})

test('gateway reads report a missing capability or failed provider as unavailable with a reason', async () => {
  assert.match((await gatewayWith({}).researchRuns()).reason, /not installed/)
  assert.match((await gatewayWith({}).backtestArtifact('bt-1')).reason, /not installed/)
  const failing = gatewayWith({ pgBacktest: { result: async () => { throw new Error('backtest compatibility API returned HTTP 500 for /backtest-lab/runs/bt-1: Traceback') } } })
  const view = await failing.backtestArtifact('bt-1')
  assert.equal(view.available, false)
  assert.equal(view.reason, 'backtest run is unavailable: the service returned HTTP 500')
  assert.deepEqual(view.metrics, [])
})

const ok = value => ({ ok: true, value })
const lostCarrier = { ok: false, error: { code: 'gateway/internal', message: 'carrier lost' } }
const view = (status, terminal = false) => ({ available: true, observedAt: 't', source: 's', terminal, run: { id: 'run-1', status } })
const collect = async (iterable, limit = 20) => { const out = []; for await (const item of iterable) { out.push(item); if (out.length >= limit) break } return out }
const noSleep = async () => {}

test('a research run is followed until terminal; a lost read keeps the last value as stale and recovers with a plain read', async () => {
  const calls = []
  const script = [ok(view('queued')), ok(view('running')), lostCarrier, ok(view('running')), ok(view('completed', true))]
  const remote = {
    researchRun: async id => { calls.push(`read:${id}`); return script.shift() },
    researchRunWait: async (id, status) => { calls.push(`wait:${status}`); return script.shift() },
  }
  const frames = await collect(followResearchRun(remote, 'run-1', new AbortController().signal, { sleep: noSleep, now: () => 0 }))
  assert.deepEqual(calls, ['read:run-1', 'wait:queued', 'wait:running', 'read:run-1', 'wait:running'])
  assert.deepEqual(frames.map(frame => frame.ok && [frame.value.run.status, frame.value.connection, frame.value.stale === true]), [
    ['queued', 'live', false], ['running', 'live', false], ['running', 'reconnecting', true], ['running', 'live', false], ['completed', 'ended', false],
  ])
  assert.equal(frames[2].value.staleReason, 'carrier lost')
})

test('a first read that fails yields the failure itself, and an unavailable answer keeps its reason', async () => {
  const failing = { researchRun: async () => lostCarrier, researchRunWait: async () => assert.fail('no wait before a value') }
  const controller = new AbortController()
  const frames = []
  for await (const frame of followResearchRun(failing, 'run-1', controller.signal, { sleep: async () => controller.abort() })) frames.push(frame)
  assert.deepEqual(frames, [lostCarrier])
  const gone = { researchRun: async () => ok({ available: false, observedAt: 't', source: 's', reason: 'research run was not found' }), researchRunWait: async () => assert.fail() }
  const c2 = new AbortController()
  const [frame] = await collect(followResearchRun(gone, 'run-1', c2.signal, { sleep: async () => c2.abort() }))
  assert.equal(frame.value.available, false)
  assert.equal(frame.value.reason, 'research run was not found')
})

test('a polled resource marks a failed refresh stale instead of dropping its value', async () => {
  const script = [ok({ available: true, runs: [1] }), ok({ available: false, reason: 'HTTP 503' }), ok({ available: true, runs: [2] })]
  const frames = await collect(pollResource(async () => script.shift(), new AbortController().signal, 1000, { sleep: noSleep, now: () => 0 }), 3)
  assert.deepEqual(frames.map(frame => [frame.value.runs[0], frame.value.stale === true, frame.value.staleReason]), [[1, false, undefined], [1, true, 'HTTP 503'], [2, false, undefined]])
})

test('resource addresses name exactly one valid id', () => {
  const address = resourceAddress(PROTOCOL.researchRun, 'run-1')
  assert.equal(address, 'dsh-resource://puregamma-research-run/run-1')
  assert.equal(resourceId(address, PROTOCOL.researchRun), 'run-1')
  for (const bad of ['dsh-resource://puregamma-research-run/', 'dsh-resource://puregamma-research-run/a/b', 'dsh-resource://puregamma-research-run/%2E%2E%2Fx', 'dsh-resource://puregamma-research-run/a?x=1', 'dsh-resource://other/run-1']) {
    assert.equal(resourceId(bad, PROTOCOL.researchRun), undefined, bad)
  }
  assert.throws(() => resourceAddress(PROTOCOL.researchRun, '../x'), /invalid/)
})

const t = key => key
const tabInfo = (contentId, opened = []) => () => ({ sidebar: { expanded: true, fullscreen: false }, panel: { id: 'p' }, tab: { id: 'tab', kind: 'k', contentId, title: 'x', visible: true, navigation: { address: contentId, params: undefined, revision: 1 }, signal: new AbortController().signal, actions: { openResource: address => opened.push(address), openTab() {}, close() {} } } })
const snapshot = (status, value, failure) => () => ({ status, value, failure })
const render = (Body, useResource, contentId = 'dsh-resource://puregamma-research-run/run-1') => renderToStaticMarkup(createElement(Body, { t, useTabInfo: tabInfo(contentId), useResource }))

test('the run view distinguishes loading, failed, unavailable, stale and live, and never shows a zero for an unreported count', () => {
  assert.match(render(ResearchRunBody, snapshot('loading')), /data-state="loading"/)
  assert.match(render(ResearchRunBody, snapshot('none')), /data-state="loading"/)
  const failed = render(ResearchRunBody, snapshot('failed', undefined, { message: 'carrier lost' }))
  assert.match(failed, /data-state="failed"/)
  assert.match(failed, /carrier lost/)
  const unavailable = render(ResearchRunBody, snapshot('live', { available: false, observedAt: 't', source: 's', reason: 'research run was not found', connection: 'reconnecting' }))
  assert.match(unavailable, /data-state="unavailable"/)
  assert.match(unavailable, /research run was not found/)
  const live = { available: true, observedAt: 't', source: 's', terminal: false, connection: 'live', run: { id: 'run-1', name: 'BTC funding', status: 'running', evidenceCount: 4 } }
  const html = render(ResearchRunBody, snapshot('live', live))
  assert.match(html, /data-state="live"/)
  assert.match(html, /data-connection="live"/)
  assert.match(html, />4</)
  assert.doesNotMatch(html, />0</, 'unreported credits/citations are not rendered as 0')
  assert.match(html, /data-missing="true"[^>]*>notReported</)
  const stale = render(ResearchRunBody, snapshot('live', { ...live, connection: 'reconnecting', stale: true, staleSince: '2026-10-29T08:01:00Z', staleReason: 'carrier lost' }))
  assert.match(stale, /data-state="stale"/)
  assert.match(stale, /stale · staleSince: 2026-10-29T08:01:00Z · carrier lost/)
  const ended = render(ResearchRunBody, snapshot('live', { ...live, terminal: true, connection: 'ended', run: { ...live.run, status: 'failed', errorMessage: 'provider timeout' } }))
  assert.match(ended, /role="alert"[^>]*>error: provider timeout/)
  assert.match(ended, /data-connection="ended"/)
})

test('artifact text is rendered as text, a failed evidence read is said, and backtests are labelled simulated', () => {
  const artifacts = { available: true, observedAt: 't', source: 's', runId: 'run-1', artifacts: [{ id: 'a1', title: 'Report', markdown: '<script>alert(1)</script>' }], evidenceAvailable: false, evidence: [] }
  const html = render(ResearchArtifactBody, snapshot('live', artifacts), 'dsh-resource://puregamma-research-artifact/run-1')
  assert.doesNotMatch(html, /<script>/)
  assert.match(html, /&lt;script&gt;/)
  assert.match(html, /data-evidence="unavailable"/)
  const backtest = { available: true, observedAt: 't', source: 's', run: { id: 'bt-1', status: 'completed', strategyName: 'Momentum' }, metrics: [{ name: 'sharpe', value: 1.83 }], artifacts: [{ id: 'f1', format: 'json', sizeBytes: 2048 }] }
  const bt = render(BacktestArtifactBody, snapshot('live', backtest), 'dsh-resource://puregamma-backtest-artifact/bt-1')
  assert.match(bt, /sharpe<\/div><div>1\.83/)
  assert.match(bt, /json · 2048 size/)
  assert.match(bt, /simulated/)
  const noMetrics = render(BacktestArtifactBody, snapshot('live', { ...backtest, metrics: [] }), 'dsh-resource://puregamma-backtest-artifact/bt-1')
  assert.match(noMetrics, /noMetrics/)
})

test('the guide page lists both indexes and opens a run through the sidebar, each with its own state', () => {
  const opened = []
  const resources = address => address.includes('research-index')
    ? { status: 'live', value: { available: true, observedAt: 't', source: 's', runs: [{ id: 'run-1', name: 'BTC funding', status: 'completed' }] } }
    : { status: 'live', value: { available: false, observedAt: 't', source: 's', reason: 'backtest capability is not installed', runs: [] } }
  const html = renderToStaticMarkup(createElement(IndexBody, { t, useTabInfo: tabInfo('sidebar://puregamma-research-index', opened), useResource: resources }))
  assert.match(html, /aria-label="open BTC funding"/)
  assert.match(html, /data-testid="puregamma-backtest-index-runs" data-state="unavailable"/)
  assert.match(html, /backtest capability is not installed/)
})

const dir = mkdtempSync(path.join(tmpdir(), 'pg-research-runs-'))
test.after(() => rmSync(dir, { recursive: true, force: true }))

test('the runs provider reads /api/research/runs with the per-user bearer file and parses the SSE stream', async () => {
  const tokenFile = path.join(dir, 'token')
  writeFileSync(tokenFile, 'user-a.token')
  chmodSync(tokenFile, 0o600)
  const seen = []
  const server = createServer((req, res) => {
    seen.push(`${req.method} ${req.url} ${req.headers.authorization}`)
    if (req.url === '/api/research/runs/run-1/events') {
      res.writeHead(200, { 'content-type': 'text/event-stream' })
      res.write('event: run.state\ndata: {"run_id":"run-1","status":"running"}\n\n: comment\n\nevent: run.comp')
      setTimeout(() => res.end('leted\ndata: {"run_id":"run-1","verified":true}\n\n'), 20)
      return
    }
    if (req.url === '/api/research/runs/missing') { res.writeHead(404, { 'content-type': 'application/json' }); res.end('{"detail":"Research run not found"}'); return }
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end(JSON.stringify(req.url.startsWith('/api/research/runs?') ? { runs: [], total: 0 } : { run: { id: 'run-1', status: 'running' } }))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  try {
    const client = createResearchRunsClient({ baseUrl: `http://127.0.0.1:${server.address().port}/`, authTokenFile: tokenFile })
    assert.equal((await client.run('run-1')).payload.run.status, 'running')
    assert.equal((await client.listRuns({ limit: 5 })).kind, 'runs')
    await assert.rejects(client.run('missing'), error => /HTTP 404/.test(error.message) && !/not found/.test(error.message))
    await assert.rejects(client.run('../x'), /invalid format/)
    const events = []
    for await (const event of client.events('run-1', new AbortController().signal)) events.push(event)
    assert.deepEqual(events.map(event => event.event), ['run.state', 'run.completed'])
    assert.deepEqual(seen.slice(0, 2), ['GET /api/research/runs/run-1 Bearer user-a.token', 'GET /api/research/runs?limit=5&offset=0 Bearer user-a.token'])
    const noToken = createResearchRunsClient({ baseUrl: `http://127.0.0.1:${server.address().port}`, authTokenFile: path.join(dir, 'absent') })
    await assert.rejects(noToken.run('run-1'), /requires bearer token/)
  } finally {
    server.close()
  }
})

test('the SSE parser tolerates CRLF, comments and malformed frames', async () => {
  const encoder = new TextEncoder()
  async function* chunks() { yield encoder.encode('event: run.state\r\ndata: {"status":"queued"}\r\n\r\ndata: not-json\n\n'); yield encoder.encode('event: run.failed\ndata: {"message":"x"}') }
  const events = []
  for await (const event of parseServerSentEvents(chunks())) events.push(event)
  assert.deepEqual(events, [{ event: 'run.state', data: { status: 'queued' } }, { event: 'run.failed', data: { message: 'x' } }])
})

test('the browser half has no transport, no credential and no write action of its own', () => {
  const read = file => readFileSync(new URL(`../plugins/ui-research-resources/src/client/${file}`, import.meta.url), 'utf8')
  // Code only: the doc comments may (and do) talk about the Host's bearer.
  const source = (read('index.ts') + read('model.ts')).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
  assert.doesNotMatch(source, /fetch\(|XMLHttpRequest|WebSocket|EventSource|localStorage|authorization|bearer|token/i)
  const called = new Set([...source.matchAll(/\bremote\.(\w+)\(/g)].map(match => match[1]))
  assert.deepEqual([...called].sort(), ['backtestArtifact', 'backtestRuns', 'researchArtifacts', 'researchRun', 'researchRunWait', 'researchRuns'], 'only the gateway reads are called')
  assert.doesNotMatch(source, /dangerouslySetInnerHTML/)
})
