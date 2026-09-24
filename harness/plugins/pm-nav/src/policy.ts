/**
 * Pure, fail-closed policy for the private Binance Portfolio Margin account.
 *
 * Architecture (deliberately one-directional):
 *
 *     Binance  ---->  riskbot  ---->  export bundle  ---->  pgPmNav  ---->  UI
 *                     (owns the        (JSON files,          (this policy;
 *                      read-only        atomically           never holds an
 *                      API key)         replaced)             exchange key)
 *
 * PureGamma holds **no** Binance credential for this account. It only reads
 * files riskbot writes into a directory mounted read-only, so a compromise of
 * the web tier cannot place, cancel or transfer anything.
 *
 * Two invariants live here, and neither is negotiable:
 *
 * 1. **Authorization is server-side.** The allowlist is evaluated on every read
 *    from the authenticated identity, never from a client-supplied field, and an
 *    unconfigured allowlist denies everybody.
 * 2. **Nothing is fabricated.** A missing, malformed, wrong-schema or stale
 *    bundle reports `available: false` (or `stale: true`) with the reason. It
 *    never becomes a zero balance, an empty NAV or a flat series.
 *
 * This module is intentionally free of Cordis and of node:fs so the safety
 * invariants can be unit-tested directly.
 */

export const LATEST_SCHEMA = 'puregamma.pm_account.v1'
export const SERIES_SCHEMA = 'puregamma.pm_nav_series.v1'

/** Bundles older than this are reported stale (riskbot reconciles every 60s). */
export const STALE_AFTER_SECONDS = 180
/** Hard cap on how long one cached read may serve a response. */
export const MAX_CACHE_SECONDS = 5

export const BUNDLE_NOT_FOUND = 'riskbot export bundle not found'

export type JsonRecord = Record<string, unknown>

export function isJsonRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function record(value: unknown): JsonRecord {
  return isJsonRecord(value) ? value : {}
}

/** Pass a provider collection through untouched; never re-model what riskbot published. */
function list(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? value : []
}

function text(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value : undefined
}

function flag(value: unknown): boolean {
  return value === true
}

function finite(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

// --------------------------------------------------------------- authorization

export function normalizeEmail(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase()
}

/**
 * The only accounts permitted to read this PM account.
 *
 * `PM_ACCOUNT_ALLOWED_EMAILS` is a comma- or semicolon-separated list. Empty
 * configuration means *deny everyone*: a misconfiguration fails closed, never
 * open. This is the single source of truth; hiding UI is not access control.
 */
export function parseAllowedEmails(raw: string | null | undefined): readonly string[] {
  const parsed: string[] = []
  for (const part of (raw ?? '').replace(/;/g, ',').split(',')) {
    const email = normalizeEmail(part)
    if (email.length > 0 && !parsed.includes(email)) parsed.push(email)
  }
  return parsed
}

export function isAllowedEmail(email: string | null | undefined, allowed: readonly string[]): boolean {
  const candidate = normalizeEmail(email)
  if (candidate.length === 0) return false
  return allowed.includes(candidate)
}

// ---------------------------------------------------------------- bundle reads

export interface BundleData {
  ok: true
  data: JsonRecord
}

export interface BundleFailure {
  ok: false
  error: string
}

export type BundleRead = BundleData | BundleFailure

/**
 * Parse one bundle file against the schema it must declare.
 *
 * riskbot writes tmp+rename so a torn read cannot happen; a malformed or
 * version-skewed file is still reported rather than guessed around.
 */
export function parseBundle(raw: string, schema: string): BundleRead {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch (error) {
    return { ok: false, error: `malformed bundle: ${error instanceof Error ? error.message : String(error)}` }
  }
  if (!isJsonRecord(parsed)) return { ok: false, error: 'bundle is not an object' }
  if (parsed.schema !== schema) {
    return { ok: false, error: `unsupported bundle schema ${JSON.stringify(parsed.schema ?? null)}` }
  }
  return { ok: true, data: parsed }
}

export function unreadableBundle(error: unknown): string {
  return `unreadable: ${error instanceof Error ? error.message : String(error)}`
}

/**
 * Age of the observation, measured from THIS process's clock.
 *
 * `snapshot.age_seconds` is relative to riskbot's process clock and is
 * meaningless here; the file mtime is what this process can verify.
 */
export function observationAgeSeconds(input: {
  observedAtMs: number | null
  snapshot: JsonRecord
  nowMs: number
}): number | null {
  if (input.observedAtMs !== null) return Math.max(0, (input.nowMs - input.observedAtMs) / 1000)
  const captured = finite(input.snapshot.captured_at_ms)
  if (captured !== undefined && captured > 0) return Math.max(0, (input.nowMs - captured) / 1000)
  return null
}

// --------------------------------------------------------------------- views

/** Provider-observed rows keep riskbot's own field names; only the envelope is normalized. */
export interface PmSourceDescriptor {
  collector: string
  readOnly: boolean
  independentOfTradingBot: boolean
  venue: string
  note: string
}

export interface PmAccountView {
  available: boolean
  reason?: string
  bundlePath: string
  label: string
  /** Always false: this private account is never merged into a user's NAV. */
  mergedIntoPortfolioNav: false
  source: PmSourceDescriptor
  stale?: boolean
  partial?: boolean
  ageSeconds?: number | null
  staleAfterSeconds?: number
  dataAsOf?: string
  generatedAt?: string
  collector?: JsonRecord
  account?: JsonRecord
  btc?: JsonRecord
  exposure?: JsonRecord
  balances?: readonly unknown[]
  positions?: readonly unknown[]
  positionsHistory?: readonly unknown[]
  positionsHistoryMeta?: JsonRecord
  orders?: readonly unknown[]
  ordersMeta?: JsonRecord
  protection?: readonly unknown[]
  risk?: JsonRecord
  coverage?: JsonRecord
  quality?: JsonRecord
  disclaimer?: string
}

export interface AccountViewInput {
  read: BundleRead
  bundlePath: string
  label: string
  /** File mtime in milliseconds, or null when the file could not be stat'd. */
  observedAtMs: number | null
  nowMs: number
}

const SOURCE: PmSourceDescriptor = {
  collector: 'riskbot',
  readOnly: true,
  independentOfTradingBot: true,
  venue: 'Binance Portfolio Margin (Classic)',
  note: '只读采集，PureGamma 不持有该账户的任何 API Key，也不具备下单/撤单能力',
}

/**
 * Everything the NAV panel needs, plus honest freshness metadata.
 *
 * `mergedIntoPortfolioNav` is set here rather than by each caller so the
 * "private account never joins the aggregate NAV" invariant cannot be dropped
 * at one call site.
 */
export function accountView(input: AccountViewInput): PmAccountView {
  const base = { bundlePath: input.bundlePath, label: input.label, mergedIntoPortfolioNav: false as const, source: SOURCE }
  if (!input.read.ok) return { available: false, reason: input.read.error, ...base }

  const payload = input.read.data
  const snapshot = record(payload.snapshot)
  const quality = record(payload.quality)
  const coverage = record(payload.coverage)
  const ordersMeta = record(payload.orders_meta)
  const risk = record(payload.risk)
  const collector = record(payload.collector)
  const ageSeconds = observationAgeSeconds({ observedAtMs: input.observedAtMs, snapshot, nowMs: input.nowMs })
  const stale = ageSeconds !== null && ageSeconds > STALE_AFTER_SECONDS
  const disclaimer = text(payload.disclaimer)

  return {
    available: true,
    ...base,
    stale: stale || flag(snapshot.is_stale),
    partial: flag(snapshot.partial) || flag(quality.partial),
    ageSeconds,
    staleAfterSeconds: STALE_AFTER_SECONDS,
    dataAsOf: text(snapshot.captured_at) ?? text(payload.generated_at),
    generatedAt: text(payload.generated_at),
    collector,
    // Official exchange figures and every provider row are passed through
    // exactly as observed.
    account: record(payload.account),
    btc: record(payload.btc),
    exposure: record(payload.exposure),
    balances: list(payload.balances),
    positions: list(payload.positions),
    positionsHistory: list(payload.positions_history),
    positionsHistoryMeta: record(payload.positions_history_meta),
    orders: list(payload.orders),
    ordersMeta: {
      capturedAt: text(ordersMeta.captured_at) ?? null,
      ageSeconds: finite(ordersMeta.age_seconds) ?? null,
      fullyCovered: typeof ordersMeta.fully_covered === 'boolean' ? ordersMeta.fully_covered : null,
      refreshIntervalSeconds: finite(ordersMeta.refresh_interval_seconds) ?? null,
    },
    protection: list(payload.protection),
    risk: {
      firingCount: finite(risk.firing_count) ?? 0,
      firing: list(risk.firing),
      drawdownPeakBtcEquivalent: risk.drawdown_peak_btc_equivalent ?? null,
      drawdownDayBtcEquivalent: risk.drawdown_day_btc_equivalent ?? null,
    },
    coverage: {
      essentialOk: coverage.essential_ok ?? null,
      ordersCovered: coverage.orders_covered ?? null,
      failures: list(coverage.failures),
      essentialFailures: list(coverage.essential_failures),
    },
    quality: {
      restOk: quality.rest_ok ?? null,
      wsConnected: quality.ws_connected ?? null,
      mismatch: quality.mismatch ?? null,
      lastError: text(quality.last_error) ?? null,
    },
    ...(disclaimer === undefined ? {} : { disclaimer }),
  }
}

export interface PmNavHistoryView {
  available: boolean
  reason?: string
  schema?: string | null
  generatedAt?: string | null
  firstPointAt?: string | null
  pointCount: number
  /** Reported so the UI can say "数据不足" instead of drawing a single dot. */
  sufficient: boolean
  windowDays?: number
  intervalHintSeconds?: number | null
  sampling?: unknown
  points: readonly unknown[]
}

/** Return only observations written by the read-only collector, gaps included. */
export function navHistoryView(read: BundleRead): PmNavHistoryView {
  if (!read.ok) {
    return { available: false, reason: read.error, points: [], pointCount: 0, sufficient: false, intervalHintSeconds: null }
  }
  const payload = read.data
  const points = list(payload.points)
  const windowDays = finite(payload.window_days)
  return {
    available: true,
    schema: text(payload.schema) ?? null,
    generatedAt: text(payload.generated_at) ?? null,
    firstPointAt: text(payload.first_point_at) ?? null,
    pointCount: finite(payload.point_count) ?? points.length,
    sufficient: points.length >= 2,
    ...(windowDays === undefined ? {} : { windowDays }),
    intervalHintSeconds: finite(payload.interval_hint_seconds) ?? null,
    sampling: payload.sampling ?? null,
    points,
  }
}
