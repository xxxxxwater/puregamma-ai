import type { PgTsyRunMode, PgTsyRuntimeSnapshot } from '@puregamma/dsh-pg-tsy-runtime'

export type HealthPath = '/healthz' | '/readyz'

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('pg-tsy health response must be an object')
  }
  return value as Record<string, unknown>
}

function bool(raw: Record<string, unknown>, key: string): boolean {
  if (typeof raw[key] !== 'boolean') throw new Error(`pg-tsy health missing boolean ${key}`)
  return raw[key] as boolean
}

/** Rust u64/usize counters must not silently lose precision in the JS JSON decoder. */
function counter(raw: Record<string, unknown>, key: string): number {
  const value = raw[key]
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`pg-tsy health missing or unsafe counter ${key}`)
  }
  return value
}

function mode(value: unknown): PgTsyRunMode {
  if (value === 'shadow' || value === 'paper' || value === 'live') return value
  throw new Error('pg-tsy health returned an unknown execution mode')
}

/**
 * Parse exactly the pinned Rust HealthSnapshot contract, not guessed fields.
 * A missing field is UNAVAILABLE, never a made-up zero/false or empty gate list.
 * This projection is observational; it cannot authorize trading.
 */
export function parsePgTsyHealth(value: unknown, path: HealthPath, status: number, source: string): PgTsyRuntimeSnapshot {
  const raw = object(value)
  const processHealthy = bool(raw, 'process_healthy')
  const ready = bool(raw, 'ready')
  const leaseHealthy = bool(raw, 'lease_healthy')
  const runMode = mode(raw.mode)
  const feedsTotal = counter(raw, 'feeds_total')
  const feedsConnected = counter(raw, 'feeds_connected')
  const eventsTotal = counter(raw, 'events_total')
  const policyDecisionsTotal = counter(raw, 'policy_decisions_total')
  const openOrders = counter(raw, 'open_orders')
  const ordersJournaledTotal = counter(raw, 'orders_journaled_total')
  if (!Array.isArray(raw.blocking_gates) || raw.blocking_gates.some(gate => typeof gate !== 'string' || !gate.trim())) {
    throw new Error('pg-tsy health returned invalid blocking_gates')
  }
  const blockingGates = [...raw.blocking_gates] as string[]
  if (raw.last_error !== null && raw.last_error !== undefined && typeof raw.last_error !== 'string') {
    throw new Error('pg-tsy health returned invalid last_error')
  }
  if (feedsConnected > feedsTotal || (ready && (!processHealthy || !leaseHealthy || blockingGates.length > 0))) {
    throw new Error('pg-tsy health returned internally inconsistent readiness')
  }
  // Pinned Rust health listener explicitly emits 200 or 503 for both endpoints.
  const expectedStatus = path === '/healthz' ? (processHealthy ? 200 : 503) : (ready ? 200 : 503)
  if (status !== expectedStatus) throw new Error(`pg-tsy ${path} HTTP status contradicts snapshot`)
  return {
    processHealthy, ready, mode: runMode, leaseHealthy, feedsTotal, feedsConnected,
    eventsTotal, policyDecisionsTotal, openOrders, ordersJournaledTotal, blockingGates,
    ...(typeof raw.last_error === 'string' && raw.last_error.trim() ? { lastError: raw.last_error.trim() } : {}),
    observedAt: new Date().toISOString(), source,
  }
}
