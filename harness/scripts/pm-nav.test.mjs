import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, utimes, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  LATEST_SCHEMA,
  SERIES_SCHEMA,
  STALE_AFTER_SECONDS,
  accountView,
  isAllowedEmail,
  navHistoryView,
  observationAgeSeconds,
  parseAllowedEmails,
  parseBundle,
} from '../plugins/pm-nav/src/policy.ts'
import { PM_ACCOUNT_NOT_AUTHORIZED, RiskbotBundleReader, RiskbotPmNavProvider } from '../plugins/pm-nav/src/index.ts'

const THREE_MAILBOXES = '  Owner@Example.com ;second@example.com,third@example.com,second@example.com '

const latestBundle = (overrides = {}) => JSON.stringify({
  schema: LATEST_SCHEMA,
  generated_at: '2026-09-21T00:00:00Z',
  collector: { name: 'riskbot', read_only: true, independent_of_trading_bot: true },
  snapshot: { captured_at: '2026-09-21T00:00:00Z', partial: false, is_stale: false },
  account: { adjusted_equity_usd: '123456.78' },
  btc: { quantity: '2.5', price_usd: '60000' },
  positions: [{ symbol: 'BTCUSDT', side: 'long', quantity: '0.5' }],
  risk: { firing_count: 0, firing: [] },
  ...overrides,
})

const seriesBundle = (points = [{ t: 1, adjusted_equity_usd: '1', btc_price_usd: '2' }]) => JSON.stringify({
  schema: SERIES_SCHEMA,
  generated_at: '2026-09-21T00:00:00Z',
  first_point_at: '2026-09-20T00:00:00Z',
  point_count: points.length,
  points,
})

/** The provider only needs the two Context members it actually uses. */
function fakeContext(services = {}) {
  return { reflect: { provide() {} }, get: name => services[name] }
}

function provider(config, services) {
  return new RiskbotPmNavProvider(fakeContext(services), config)
}

// ------------------------------------------------------------------ allowlist

test('the allowlist accepts the configured mailboxes and nothing else', () => {
  const allowed = parseAllowedEmails(THREE_MAILBOXES)
  assert.deepEqual(allowed, ['owner@example.com', 'second@example.com', 'third@example.com'])
  for (const email of ['Owner@Example.com', 'second@example.com', 'third@example.com']) {
    assert.equal(isAllowedEmail(email, allowed), true, email)
  }
  for (const email of ['fourth@example.com', '', '  ', null, undefined, 'owner@example.com.evil.com']) {
    assert.equal(isAllowedEmail(email, allowed), false, String(email))
  }
})

test('an unconfigured allowlist denies everyone instead of opening up', () => {
  for (const raw of ['', '   ', ',', ';', null, undefined]) {
    const allowed = parseAllowedEmails(raw)
    assert.deepEqual(allowed, [])
    assert.equal(isAllowedEmail('owner@example.com', allowed), false, JSON.stringify(raw))
  }
})

// -------------------------------------------------------------------- bundles

test('a bundle is only accepted when it is an object declaring the expected schema', () => {
  assert.equal(parseBundle('{"schema":"other"}', LATEST_SCHEMA).ok, false)
  assert.equal(parseBundle('not json', LATEST_SCHEMA).ok, false)
  assert.equal(parseBundle('[1,2]', LATEST_SCHEMA).ok, false)
  assert.equal(parseBundle('{"schema":null}', LATEST_SCHEMA).ok, false)
  assert.equal(parseBundle(latestBundle(), LATEST_SCHEMA).ok, true)
  // A v2 bundle must never be read as v1.
  assert.equal(parseBundle(seriesBundle(), LATEST_SCHEMA).ok, false)
})

test('age is measured from the file mtime this process can verify, not the collector clock', () => {
  const snapshot = { captured_at_ms: 5_000 }
  assert.equal(observationAgeSeconds({ observedAtMs: 1_000, snapshot, nowMs: 61_000 }), 60)
  assert.equal(observationAgeSeconds({ observedAtMs: null, snapshot, nowMs: 65_000 }), 60)
  assert.equal(observationAgeSeconds({ observedAtMs: null, snapshot: {}, nowMs: 65_000 }), null)
  // A future mtime never yields a negative age.
  assert.equal(observationAgeSeconds({ observedAtMs: 90_000, snapshot, nowMs: 61_000 }), 0)
})

// ---------------------------------------------------------------- fail closed

test('a missing, malformed or version-skewed bundle reports unavailable and invents no figures', () => {
  const nowMs = Date.parse('2026-09-21T00:00:00Z')
  const cases = [
    { ok: false, error: 'riskbot export bundle not found' },
    { ok: false, error: 'bundle is not an object' },
    { ok: false, error: "unsupported bundle schema 'puregamma.pm_account.v2'" },
  ]
  for (const read of cases) {
    const view = accountView({ read, bundlePath: '/var/lib/puregamma/riskbot/latest.json', label: 'Binance Portfolio Margin', observedAtMs: null, nowMs })
    assert.equal(view.available, false)
    assert.equal(view.reason, read.error)
    // No fabricated zeros, no empty collections pretending to be a real account.
    assert.equal('account' in view, false)
    assert.equal('positions' in view, false)
    assert.equal('risk' in view, false)
    assert.equal('ageSeconds' in view, false)
    // The two invariants survive every failure path.
    assert.equal(view.mergedIntoPortfolioNav, false)
    assert.equal(view.source.readOnly, true)
  }
})

test('an aged bundle is reported stale rather than silently presented as live', () => {
  const nowMs = 1_000_000
  const read = parseBundle(latestBundle(), LATEST_SCHEMA)
  const fresh = accountView({ read, bundlePath: 'latest.json', label: 'l', observedAtMs: nowMs - 1_000, nowMs })
  assert.equal(fresh.available, true)
  assert.equal(fresh.stale, false)
  assert.equal(fresh.ageSeconds, 1)
  assert.equal(fresh.dataAsOf, '2026-09-21T00:00:00Z')

  const aged = accountView({ read, bundlePath: 'latest.json', label: 'l', observedAtMs: nowMs - (STALE_AFTER_SECONDS + 1) * 1000, nowMs })
  assert.equal(aged.available, true)
  assert.equal(aged.stale, true)
  assert.ok(aged.ageSeconds > STALE_AFTER_SECONDS)
})

test('the collector is trusted only about staleness, never about freshness', () => {
  const nowMs = 1_000_000
  const read = parseBundle(latestBundle({ snapshot: { captured_at: 'x', is_stale: true, partial: true } }), LATEST_SCHEMA)
  const view = accountView({ read, bundlePath: 'latest.json', label: 'l', observedAtMs: nowMs, nowMs })
  assert.equal(view.stale, true)
  assert.equal(view.partial, true)
})

test('observed provider rows are passed through unchanged and never re-invented', () => {
  const nowMs = 1_000_000
  const read = parseBundle(latestBundle(), LATEST_SCHEMA)
  const view = accountView({ read, bundlePath: 'latest.json', label: 'Binance Portfolio Margin', observedAtMs: nowMs, nowMs })
  assert.deepEqual(view.account, { adjusted_equity_usd: '123456.78' })
  assert.deepEqual(view.positions, [{ symbol: 'BTCUSDT', side: 'long', quantity: '0.5' }])
  assert.equal(view.label, 'Binance Portfolio Margin')
  assert.equal(view.mergedIntoPortfolioNav, false)
})

test('NAV history is unavailable, not empty, when the series is missing', () => {
  const missing = navHistoryView({ ok: false, error: 'riskbot export bundle not found' })
  assert.equal(missing.available, false)
  assert.deepEqual(missing.points, [])
  assert.equal(missing.sufficient, false)
  assert.equal(missing.intervalHintSeconds, null)

  const single = navHistoryView(parseBundle(seriesBundle([{ t: 1 }]), SERIES_SCHEMA))
  assert.equal(single.available, true)
  assert.equal(single.sufficient, false, 'one observation must not be drawn as a curve')

  const pair = navHistoryView(parseBundle(seriesBundle([{ t: 1 }, { t: 2 }]), SERIES_SCHEMA))
  assert.equal(pair.sufficient, true)
  assert.equal(pair.pointCount, 2)
})

// ------------------------------------------------------------- real fs reader

test('the reader reports the outage when the bundle is missing and recovers when it appears', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pm-nav-'))
  try {
    const reader = new RiskbotBundleReader(directory)
    const missing = await reader.read('latest.json', LATEST_SCHEMA)
    assert.equal(missing.read.ok, false)
    assert.equal(missing.read.error, 'riskbot export bundle not found')
    assert.equal(missing.mtimeMs, null)

    await writeFile(join(directory, 'latest.json'), latestBundle(), 'utf8')
    const found = await reader.read('latest.json', LATEST_SCHEMA)
    assert.equal(found.read.ok, true)
    assert.ok(found.mtimeMs > 0)

    // A torn/version-skewed write is reported, and the previous good copy is not
    // silently reused as if it were current.
    await writeFile(join(directory, 'latest.json'), latestBundle({ schema: 'puregamma.pm_account.v2' }), 'utf8')
    const skewed = await reader.read('latest.json', LATEST_SCHEMA)
    assert.equal(skewed.read.ok, false)
    assert.match(String(skewed.read.error), /unsupported bundle schema/)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test('an aged file on disk is served, but marked stale', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pm-nav-'))
  try {
    const path = join(directory, 'latest.json')
    await writeFile(path, latestBundle(), 'utf8')
    const past = new Date(Date.now() - (STALE_AFTER_SECONDS + 60) * 1000)
    await utimes(path, past, past)
    const reader = new RiskbotBundleReader(directory)
    const read = await reader.read('latest.json', LATEST_SCHEMA)
    const view = accountView({ read: read.read, bundlePath: path, label: 'l', observedAtMs: read.mtimeMs, nowMs: Date.now() })
    assert.equal(view.available, true)
    assert.equal(view.stale, true)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

// ------------------------------------------------------- server-side authorization

test('without an installed auth capability the private account is refused', async () => {
  const nav = provider({ allowedEmails: THREE_MAILBOXES }, {})
  const view = await nav.account()
  assert.equal(view.available, false)
  assert.equal(view.reason, PM_ACCOUNT_NOT_AUTHORIZED)
  assert.equal((await nav.navHistory()).reason, PM_ACCOUNT_NOT_AUTHORIZED)
})

test('an unauthenticated, failing or unlisted session is refused', async () => {
  const allowedEmails = THREE_MAILBOXES
  const failing = provider({ allowedEmails }, { pgAuth: { currentUser: async () => { throw new Error('no session') } } })
  assert.equal((await failing.account()).reason, PM_ACCOUNT_NOT_AUTHORIZED)

  const unlisted = provider({ allowedEmails }, { pgAuth: { currentUser: async () => ({ email: 'fourth@example.com' }) } })
  assert.equal((await unlisted.account()).reason, PM_ACCOUNT_NOT_AUTHORIZED)

  // An empty deployment configuration refuses the owner too.
  const unconfigured = provider({ allowedEmails: '' }, { pgAuth: { currentUser: async () => ({ email: 'owner@example.com' }) } })
  assert.equal((await unconfigured.account()).reason, PM_ACCOUNT_NOT_AUTHORIZED)
})

test('an unauthorized caller never causes the private bundle to be read', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pm-nav-'))
  try {
    await writeFile(join(directory, 'latest.json'), latestBundle(), 'utf8')
    await writeFile(join(directory, 'series.json'), seriesBundle(), 'utf8')
    const nav = provider({ riskbotExportDir: directory, allowedEmails: THREE_MAILBOXES }, {
      pgAuth: { currentUser: async () => ({ email: 'fourth@example.com' }) },
    })
    const view = await nav.account()
    assert.equal(view.available, false)
    // The refusal carries no account data at all, even though the file is present.
    assert.equal('account' in view, false)
    assert.equal('btc' in view, false)
    assert.deepEqual((await nav.navHistory()).points, [])
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test('each configured mailbox reads the same published bundle', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'pm-nav-'))
  try {
    await writeFile(join(directory, 'latest.json'), latestBundle(), 'utf8')
    await writeFile(join(directory, 'series.json'), seriesBundle([{ t: 1 }, { t: 2 }]), 'utf8')
    for (const email of ['owner@example.com', 'second@example.com', 'third@example.com']) {
      const nav = provider({ riskbotExportDir: directory, allowedEmails: THREE_MAILBOXES }, {
        pgAuth: { currentUser: async () => ({ email }) },
      })
      assert.deepEqual(nav.allowedEmails(), ['owner@example.com', 'second@example.com', 'third@example.com'])
      const view = await nav.account()
      assert.equal(view.available, true, email)
      assert.equal(view.mergedIntoPortfolioNav, false, email)
      assert.equal(view.available && view.account.adjusted_equity_usd, '123456.78', email)
      assert.equal((await nav.navHistory()).sufficient, true, email)
    }
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})
