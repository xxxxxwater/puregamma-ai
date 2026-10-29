import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import test from 'node:test'
import { Context } from '@deepseek-ai/cordis'
import MarketDataService from '../plugins/market-data/src/index.ts'
import PortfolioService from '../plugins/portfolio/src/index.ts'
import { mountHarness } from './parity/harness-reads.mjs'

// Unit tests for the Market Data and Portfolio slices (service contracts,
// compatibility providers, model-facing tools). Legacy-vs-Harness parity on
// real FastAPI responses lives in market-portfolio-parity.test.mjs.

async function withLegacy(routes, body) {
  const server = createServer((req, res) => {
    const route = routes[req.url.split('?')[0]]
    if (!route) { res.writeHead(404); res.end('{}'); return }
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end(JSON.stringify(typeof route === 'function' ? route(req) : route))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  process.env.PUREGAMMA_LEGACY_API_TOKEN = 'unit.token'
  const harness = await mountHarness({ baseUrl: `http://127.0.0.1:${server.address().port}`, authTokenFile: undefined })
  try {
    return await body(harness)
  } finally {
    harness.dispose()
    server.close()
  }
}

test('service definitions register under their stable Cordis names and leave with their plugin', async () => {
  class FakeMarket extends MarketDataService {
    async snapshot() { return { quotes: [], asOf: 't' } }
    async quote() { return undefined }
    async news() { return [] }
    async health() { return [] }
  }
  class FakePortfolio extends PortfolioService {
    async snapshot() { throw new Error('unused') }
    async accounts() { return [] }
    async positions() { return [] }
    async nav() { return { currency: 'USD', nav: null, cash: null, positionsValue: null, calculatedAt: 't', calculationVersion: 'v', stale: false, reason: 'none' } }
  }
  const root = new Context()
  const forks = [root.plugin(FakeMarket), root.plugin(FakePortfolio)]
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.ok(root.get('pgMarketData') instanceof MarketDataService)
  assert.ok(root.get('pgPortfolio') instanceof PortfolioService)
  for (const fork of forks) fork.dispose()
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.equal(root.get('pgMarketData'), undefined)
  assert.equal(root.get('pgPortfolio'), undefined)
})

test('market provider: asset classes map, incomplete rows are skipped, numbers become decimal strings', () => withLegacy({
  '/market/snapshot': { assets: [
    { symbol: 'aapl', price: 230.1, timestamp: '2026-10-29T11:59:00Z', source: 'polygon', is_realtime: true, asset_type: 'equity' },
    { symbol: 'EURUSD', price: '1.0842', timestamp: '2026-10-29T11:59:00Z', source: 'oanda', is_realtime: true, asset_type: 'forex' },
    { symbol: 'XAU', price: 2650, timestamp: '2026-10-29T11:59:00Z', source: 'lbma', is_realtime: false, asset_type: 'metal' },
    { symbol: 'NOPRICE', timestamp: '2026-10-29T11:59:00Z', source: 'x', is_realtime: true },
    { symbol: 'NOTIME', price: 1, source: 'x', is_realtime: true },
    { symbol: 'NAN', price: Number.NaN, timestamp: '2026-10-29T11:59:00Z', source: 'x', is_realtime: true },
  ] },
}, async harness => {
  const { value } = await harness.run('market_snapshot', { instruments: [] })
  assert.deepEqual(value.quotes.map(row => [row.symbol, row.assetClass, row.last, row.stale]), [['AAPL', 'equity', '230.1', false], ['EURUSD', 'fx', '1.0842', false], ['XAU', 'commodity', '2650', true]])
  const one = await harness.services.pgMarketData.quote({ symbol: 'aapl', venue: 'auto', assetClass: 'equity' })
  assert.equal(one.last, '230.1')
  assert.equal(await harness.services.pgMarketData.quote({ symbol: 'TSLA', venue: 'auto', assetClass: 'equity' }), undefined, 'a missing symbol is absent, not zero')
}))

test('market provider refuses a payload without an assets array instead of reporting an empty market', () => withLegacy({ '/market/snapshot': { assets: null } }, async harness => {
  await assert.rejects(harness.run('market_snapshot', { instruments: [] }), /no assets array/)
}))

test('portfolio provider: venue-precision decimal strings survive, sides normalise, ambiguous positions carry no account', () => withLegacy({
  '/portfolio': { connected: true, stale: false, data_as_of: '2026-10-29T11:00:00+00:00', nav: '1234567.8912', available_cash: '45000.00', holdings: [{ value: 1000 }, { value: 'x' }],
    accounts: [
      { id: 'a1', provider: 'IBKR', name: 'One', status: 'CONNECTED', nav: 1, available_cash: 1, as_of: '2026-10-29T11:00:00+00:00' },
      { id: 'a2', provider: 'ibkr', name: 'Two', status: 'CONNECTED', nav: 2, available_cash: 2, as_of: '2026-10-29T11:00:00+00:00' },
      { id: 'a3', provider: 'evm', name: 'Three', status: 'STALE', nav: 3, available_cash: 3, as_of: '2026-10-28T11:00:00+00:00' },
    ],
    positions: [
      { symbol: 'SPY', venue: 'ibkr', side: 'LONG', quantity: '10.000000001', mark_price: 580.5, unrealized_pnl: 12 },
      { symbol: 'ETH', venue: 'evm', side: 'sideways', quantity: 1.5, mark_price: 2500 },
      { symbol: 'BAD', venue: 'evm', quantity: 'x' },
    ] },
}, async harness => {
  const snapshot = await harness.services.pgPortfolio.snapshot()
  assert.equal(snapshot.nav.nav, '1234567.8912')
  assert.equal(snapshot.nav.cash, '45000.00')
  assert.equal(snapshot.nav.positionsValue, '1000', 'holdings sum only numeric values')
  assert.deepEqual(snapshot.accounts.map(row => [row.id, row.provider, row.stale]), [['a1', 'ibkr', false], ['a2', 'ibkr', false], ['a3', 'evm', true]])
  assert.deepEqual(snapshot.positions.map(row => [row.instrument, row.accountId, row.side, row.quantity, row.stale]), [['SPY', undefined, 'long', '10.000000001', false], ['ETH', 'a3', undefined, '1.5', true]])
  const filtered = await harness.services.pgPortfolio.nav({ accountIds: [' a1 ', 'a2'].map(id => id.trim()) })
  assert.equal(filtered.nav, '3')
  assert.equal(filtered.cash, '3')
  assert.equal(filtered.positionsValue, '0')
}))

test('portfolio provider: a filtered read never labels another account\'s position, and sums decimals exactly', () => withLegacy({
  '/portfolio': { connected: true, stale: false, data_as_of: '2026-10-29T11:00:00+00:00', nav: '300.3', available_cash: '30.3',
    accounts: [
      { id: 'a', provider: 'binance', status: 'CONNECTED', nav: 100.1, available_cash: 10.1, as_of: '2026-10-29T11:00:00+00:00' },
      { id: 'b', provider: 'binance', status: 'CONNECTED', nav: 200.2, available_cash: 20.2, as_of: '2026-10-29T11:00:00+00:00' },
      { id: 'c', provider: 'ibkr', status: 'CONNECTED', nav: 0.1, available_cash: 0.2, as_of: '2026-10-29T11:00:00+00:00' },
    ],
    positions: [
      { symbol: 'BTC', venue: 'binance', side: 'long', quantity: '1' },
      { symbol: 'SPY', venue: 'ibkr', side: 'long', quantity: '2' },
    ] },
}, async harness => {
  // Two accounts share binance: the BTC position may be b's, so a read of a alone omits it.
  const onlyA = await harness.services.pgPortfolio.snapshot({ accountIds: ['a'] })
  assert.deepEqual(onlyA.positions, [])
  const both = await harness.services.pgPortfolio.snapshot({ accountIds: ['a', 'b'] })
  assert.deepEqual(both.positions.map(row => [row.instrument, row.accountId]), [['BTC', undefined]])
  const onlyC = await harness.services.pgPortfolio.snapshot({ accountIds: ['c'] })
  assert.deepEqual(onlyC.positions.map(row => [row.instrument, row.accountId]), [['SPY', 'c']])
  const nav = await harness.services.pgPortfolio.nav({ accountIds: ['a', 'b'] })
  assert.equal(nav.nav, '300.3')
  assert.equal(nav.cash, '30.3')
  assert.equal(nav.positionsValue, '270')
  assert.equal((await harness.services.pgPortfolio.nav({ accountIds: ['c'] })).positionsValue, '-0.1')
}))

test('portfolio tools: stale is said and presentation meta carries the server figure verbatim', () => withLegacy({
  '/portfolio': req => req.headers.authorization === 'Bearer unit.token'
    ? { connected: true, stale: true, data_as_of: '2026-10-29T11:00:00Z', nav: 10, available_cash: 2, accounts: [{ id: 'a1', provider: 'plaid', status: 'STALE', nav: 10, available_cash: 2, as_of: '2026-10-29T11:00:00Z' }] }
    : { connected: false },
}, async harness => {
  const nav = await harness.run('portfolio_nav', { accountIds: [] })
  assert.match(nav.text, /^NAV 10 USD; cash 2; calculated 2026-10-29T11:00:00\.000Z \(stale\)\.$/)
  assert.deepEqual([nav.meta.schema, nav.meta.available, nav.meta.stale, nav.meta.positions], ['puregamma.portfolio.nav/v1', true, true, null])
  const snapshot = await harness.run('portfolio_snapshot', { accountIds: [] })
  assert.match(snapshot.text, /NAV 10 USD, cash 2, 0 positions \(stale\)/)
  assert.equal(snapshot.meta.positions, 0)
}))
