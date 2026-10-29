import assert from 'node:assert/strict'
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { mountHarness, readThroughHarness } from './parity/harness-reads.mjs'

// Legacy-vs-Harness parity for Market Data and Portfolio, Harness half.
//
// fixtures/legacy-parity.json holds the real FastAPI responses for fixed
// scenarios; tests/harness/test_market_portfolio_parity.py fails when FastAPI
// stops producing exactly these bytes and also runs the same reads live. Here
// the real compatibility providers (mounted in a Cordis Context) and the real
// model-facing tools read those responses over HTTP. The rules: same fields as
// decimal strings, same freshness, unavailable stays unavailable with a
// reason, and a missing NAV/cash is never rendered as 0.

const golden = JSON.parse(readFileSync(new URL('./fixtures/legacy-parity.json', import.meta.url), 'utf8'))
const dir = mkdtempSync(path.join(tmpdir(), 'pg-parity-'))
const tokenFile = name => {
  const file = path.join(dir, name)
  writeFileSync(file, name)
  chmodSync(file, 0o600)
  return file
}
const state = { market: 'live', fail: undefined }
const server = createServer((req, res) => {
  const send = (status, body) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)) }
  if (state.fail !== undefined) return send(state.fail, { detail: 'boom at /srv/internal' })
  if (req.url === '/market/snapshot') return send(200, golden.market[state.market])
  if (req.url === '/health') return send(200, { ok: true })
  if (req.url === '/portfolio') {
    const scenario = (req.headers.authorization ?? '').replace(/^Bearer /, '')
    return scenario in golden.portfolio ? send(200, golden.portfolio[scenario]) : send(401, { detail: 'unauthorized' })
  }
  if (req.url?.startsWith('/api/news?')) return send(200, { items: [{ id: 'n1', provider: 'coindesk', title: 'BTC funding flips', published_at: '2026-10-29T11:00:00Z', symbols: ['BTC'], url: 'https://example.com/n1' }, { id: 'n2', title: 'no time' }] })
  return send(404, { detail: 'not found' })
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const baseUrl = `http://127.0.0.1:${server.address().port}`
test.after(() => { server.close(); rmSync(dir, { recursive: true, force: true }) })

const same = (harness, legacy) => typeof harness === 'string' && Number(harness) === Number(legacy)
const utc = value => new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`).toISOString()
const read = async (scenario, accountIds = []) => { state.market = 'live'; return readThroughHarness({ baseUrl, authTokenFile: tokenFile(scenario), accountIds }) }

test('connected: NAV, cash, accounts and positions are the legacy values; staleness and as-of carry over', async () => {
  const legacy = golden.portfolio.connected
  const harness = await read('connected')
  const nav = harness.portfolioNavTool.value
  assert.equal(nav.available, true)
  assert.ok(same(nav.nav, legacy.nav) && same(nav.cash, legacy.available_cash))
  assert.equal(nav.stale, legacy.stale)
  assert.equal(nav.calculatedAt, utc(legacy.data_as_of))
  assert.equal(harness.portfolioNavTool.meta.nav, nav.nav)
  assert.match(harness.portfolioNavTool.text, new RegExp(`^NAV ${nav.nav} USD`))
  const accounts = new Map(harness.portfolioSnapshotTool.value.accounts.map(row => [row.id, row]))
  for (const row of legacy.accounts) {
    const mine = accounts.get(row.id)
    assert.deepEqual([mine.provider, mine.label, mine.status, mine.observedAt, mine.stale], [row.provider, row.name, row.status, utc(row.as_of), row.status === 'STALE'])
  }
  const positions = harness.portfolioSnapshotTool.value.positions
  assert.equal(positions.length, legacy.positions.length)
  for (const row of legacy.positions) {
    const mine = positions.find(item => item.instrument === row.symbol && item.side === row.side)
    assert.ok(same(mine.quantity, row.quantity) && same(mine.markPrice, row.mark_price) && same(mine.unrealizedPnl, row.unrealized_pnl))
    assert.equal(mine.source, `compatibility:${row.venue}`)
  }
  // portfolio_positions reports the same rows (plus each row's currency).
  assert.deepEqual(harness.portfolioPositionsTool.value.positions.map(({ currency, ...row }) => (assert.equal(currency, 'USD'), row)), harness.portfolioSnapshotTool.value.positions)
})

test('a filtered read reports the selected accounts\' own NAV and freshness, not the all-account total', async () => {
  const legacy = golden.portfolio.connected.accounts
  const hl = await read('connected', ['acct-hl'])
  assert.ok(same(hl.portfolioNavTool.value.nav, legacy.find(row => row.id === 'acct-hl').nav))
  assert.equal(hl.portfolioNavTool.value.stale, false)
  assert.deepEqual(hl.portfolioService.accounts.map(row => row.id), ['acct-hl'])
  const plaid = await read('connected', ['acct-plaid'])
  assert.ok(same(plaid.portfolioNavTool.value.nav, legacy.find(row => row.id === 'acct-plaid').nav))
  assert.equal(plaid.portfolioNavTool.value.stale, true)
  const unknown = await read('connected', ['acct-someone-else'])
  assert.equal(unknown.portfolioNavTool.value.available, false)
  assert.equal(unknown.portfolioNavTool.value.nav, undefined)
})

test('partial: a connected account without a snapshot is unknown, never a zero balance', async () => {
  const legacy = golden.portfolio.partial
  assert.equal(legacy.accounts.find(row => row.id === 'acct-evm').available_cash, 0, 'the legacy payload says 0.0 for it')
  const harness = await read('partial')
  assert.ok(same(harness.portfolioNavTool.value.nav, legacy.nav))
  assert.match(harness.portfolioNavTool.value.reason, /excludes 1 connected account without a snapshot/)
  assert.deepEqual(harness.portfolioService.cash.map(row => row.accountId), ['acct-ibkr'])
  const evm = harness.portfolioService.accounts.find(row => row.id === 'acct-evm')
  assert.equal(evm.observedAt, undefined)
})

test('no account: unavailable with a reason on every surface; the legacy 0 never appears', async () => {
  assert.equal(golden.portfolio.none.nav, 0, 'legacy reports NAV 0 with connected=false')
  const harness = await read('none')
  for (const tool of [harness.portfolioNavTool, harness.portfolioSnapshotTool]) {
    assert.equal(tool.value.available, false)
    assert.equal(tool.value.nav, undefined)
    assert.equal(tool.value.cash, undefined)
    assert.equal(tool.meta.nav, null)
    assert.equal(tool.meta.available, false)
    assert.equal(tool.meta.reason, 'no connected portfolio snapshot')
    assert.doesNotMatch(tool.text, /\b0(\.0+)? USD|NAV 0\b/)
  }
  assert.match(harness.portfolioNavTool.text, /^NAV unavailable: no connected portfolio snapshot/)
  assert.equal(harness.portfolioService.nav.nav, null)
})

test('market: same symbols, prices, times and sources; non-realtime quotes are stale', async () => {
  const harness = await read('connected')
  const legacy = golden.market.live.assets
  const quotes = harness.marketSnapshotTool.value.quotes
  assert.deepEqual(quotes.map(row => row.symbol), legacy.map(row => row.symbol))
  for (const asset of legacy) {
    const mine = quotes.find(row => row.symbol === asset.symbol)
    assert.ok(same(mine.last, asset.price) && same(mine.volume24h, asset.volume_24h))
    assert.deepEqual([mine.observedAt, mine.source, mine.venue, mine.assetClass, mine.stale], [asset.timestamp, asset.source, asset.source, asset.asset_type, !asset.is_realtime])
  }
  assert.equal(harness.marketSnapshotTool.value.asOf, new Date(Math.max(...legacy.map(row => Date.parse(row.timestamp)))).toISOString())
  assert.match(harness.marketSnapshotTool.text, /ETH: 2500\.25 \(kraken, stale\)/)
})

test('market maxAgeMs marks old realtime quotes stale instead of hiding them', async () => {
  const harness = await mountHarness({ baseUrl, authTokenFile: tokenFile('connected') })
  try {
    state.market = 'live'
    const fresh = await harness.run('market_snapshot', { instruments: [{ symbol: 'btc', venue: 'auto', assetClass: 'crypto' }] })
    assert.deepEqual(fresh.value.quotes.map(row => [row.symbol, row.stale]), [['BTC', false]])
    const old = await harness.run('market_snapshot', { instruments: [{ symbol: 'BTC', venue: 'auto', assetClass: 'crypto' }], maxAgeMs: 1 })
    assert.deepEqual(old.value.quotes.map(row => [row.symbol, row.stale]), [['BTC', true]])
    await assert.rejects(harness.run('market_snapshot', { instruments: [], maxAgeMs: -1 }), /non-negative/)
  } finally {
    harness.dispose()
  }
})

test('market mock mode: invented prices never reach the tools', async () => {
  assert.equal(golden.market.mock.assets[0].is_mock, true)
  const harness = await mountHarness({ baseUrl, authTokenFile: tokenFile('connected') })
  try {
    state.market = 'mock'
    const result = await harness.run('market_snapshot', { instruments: [] })
    assert.deepEqual(result.value.quotes, [])
    assert.match(result.text, /no matching instruments/)
  } finally {
    harness.dispose()
    state.market = 'live'
  }
})

test('a failing or unauthorized legacy API fails the tool explicitly, with no fallback figure', async () => {
  const harness = await mountHarness({ baseUrl, authTokenFile: tokenFile('connected') })
  try {
    state.fail = 500
    await assert.rejects(harness.run('portfolio_nav', { accountIds: [] }), error => /HTTP 500/.test(error.message) && !/srv\/internal/.test(error.message))
    await assert.rejects(harness.run('market_snapshot', { instruments: [] }), /HTTP 500/)
    const health = await harness.run('market_provider_health', {})
    assert.deepEqual(health.value.providers.map(row => row.state), ['unavailable', 'unavailable'])
  } finally {
    state.fail = undefined
    harness.dispose()
  }
  const stranger = await mountHarness({ baseUrl, authTokenFile: tokenFile('nobody') })
  try {
    await assert.rejects(stranger.run('portfolio_nav', { accountIds: [] }), /HTTP 401/)
  } finally {
    stranger.dispose()
  }
  const signedOut = await mountHarness({ baseUrl, authTokenFile: path.join(dir, 'absent') })
  try {
    await assert.rejects(signedOut.run('portfolio_snapshot', { accountIds: [] }), /requires bearer token/)
    await assert.rejects(signedOut.run('market_news', { symbols: [] }), /requires bearer token/)
    const health = await signedOut.run('market_provider_health', {})
    assert.deepEqual(health.value.providers.map(row => [row.provider, row.state]), [['legacy-puregamma-api', 'healthy'], ['legacy-puregamma-news', 'unavailable']])
  } finally {
    signedOut.dispose()
  }
})

test('market news keeps attribution and drops items without an id, title or time', async () => {
  const harness = await mountHarness({ baseUrl, authTokenFile: tokenFile('connected') })
  try {
    const result = await harness.run('market_news', { symbols: ['btc'], limit: 5 })
    assert.deepEqual(result.value.items, [{ id: 'n1', source: 'coindesk', title: 'BTC funding flips', url: 'https://example.com/n1', publishedAt: '2026-10-29T11:00:00Z', symbols: ['BTC'] }])
    await assert.rejects(harness.run('market_news', { symbols: [], limit: 51 }), /1 to 50/)
  } finally {
    harness.dispose()
  }
})

test('the providers are Cordis lifecycle-owned: disposing the plugin removes the service', async () => {
  const harness = await mountHarness({ baseUrl, authTokenFile: tokenFile('connected') })
  assert.deepEqual(harness.mounted(), { pgMarketData: true, pgPortfolio: true })
  harness.dispose()
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.deepEqual(harness.mounted(), { pgMarketData: false, pgPortfolio: false })
})
