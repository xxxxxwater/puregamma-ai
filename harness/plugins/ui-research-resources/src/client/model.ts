import type { RemoteResult } from '@deepseek-ai/dsh-typert-protocol'
import type { PureGammaResearchRunView } from '@puregamma/dsh-client-gateway'

/**
 * Resource addresses and the browser-side follow loops. Pure: no React, no
 * Cordis, no transport of its own — every read goes through the injected
 * Remote calls, so the bearer never leaves the Host.
 */

export const PROTOCOL = {
  researchRun: 'puregamma-research-run',
  researchArtifact: 'puregamma-research-artifact',
  backtestArtifact: 'puregamma-backtest-artifact',
  researchIndex: 'puregamma-research-index',
  backtestIndex: 'puregamma-backtest-index',
} as const
export type ProtocolName = typeof PROTOCOL[keyof typeof PROTOCOL]

const ID = /^(?!\.+$)[A-Za-z0-9._:-]{1,160}$/

export function resourceAddress(protocol: ProtocolName, id: string): string {
  if (!ID.test(id)) throw new Error('resource id has an invalid format')
  return `dsh-resource://${protocol}/${encodeURIComponent(id)}`
}

/** The id an address names for `protocol`, or `undefined` when it is not exactly one valid segment. */
export function resourceId(address: string, protocol: ProtocolName): string | undefined {
  const prefix = `dsh-resource://${protocol}/`
  if (typeof address !== 'string' || !address.startsWith(prefix)) return undefined
  const segment = address.slice(prefix.length)
  if (!segment || /[/?#]/.test(segment)) return undefined
  let id: string
  try {
    id = decodeURIComponent(segment)
  } catch {
    return undefined
  }
  return ID.test(id) ? id : undefined
}

/** What every resource view adds client-side: whether the shown value is a last-known copy. */
export interface Freshness {
  /** The last read failed; the value is the last one that succeeded. */
  stale?: boolean
  staleSince?: string
  /** Why the latest read failed, when the value is stale. */
  staleReason?: string
}

export type LiveResearchRunView = PureGammaResearchRunView & Freshness & {
  /** `live` while following, `reconnecting` after a lost read, `ended` once the run is terminal. */
  connection: 'live' | 'reconnecting' | 'ended'
}

export interface ResearchRunRemote {
  researchRun(runId: string): Promise<RemoteResult<PureGammaResearchRunView>>
  researchRunWait(runId: string, knownStatus: string): Promise<RemoteResult<PureGammaResearchRunView>>
}

export interface FollowOptions {
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>
  now?: () => number
  /** Lower bound between two reads of a run that has not changed. */
  minIntervalMs?: number
  /** Ceiling of the exponential backoff after failed reads. */
  maxBackoffMs?: number
}

export function wait(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve()
  return new Promise(resolve => {
    const done = (): void => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve() }
    const timer = setTimeout(done, ms)
    signal.addEventListener('abort', done, { once: true })
  })
}

export function backoff(failures: number, maxMs = 30000): number {
  return Math.min(maxMs, 1000 * 2 ** Math.max(0, Math.min(failures - 1, 10)))
}

function failureText(result: RemoteResult<unknown>): string | undefined {
  return result.ok ? undefined : result.error.message
}

/**
 * Follow one research run until it is terminal.
 *
 * The first read and every read after a failure are plain authoritative reads
 * (`researchRun`); in between, `researchRunWait` long-polls the Host, which
 * follows the server's SSE stream. A failed read never erases what is known:
 * with no value yet it yields the failure, otherwise it yields the last value
 * marked stale/reconnecting and retries with backoff, then recovers with a
 * plain read. A terminal run ends the stream.
 */
export async function* followResearchRun(remote: ResearchRunRemote, runId: string, signal: AbortSignal, options: FollowOptions = {}): AsyncIterable<RemoteResult<LiveResearchRunView>> {
  const sleep = options.sleep ?? wait
  const now = options.now ?? Date.now
  const minIntervalMs = options.minIntervalMs ?? 3000
  let last: LiveResearchRunView | undefined
  let failures = 0
  let recover = true
  while (!signal.aborted) {
    const started = now()
    const status = last?.run?.status
    const result = recover || status === undefined ? await remote.researchRun(runId) : await remote.researchRunWait(runId, status)
    if (signal.aborted) return
    const lost = !result.ok || !result.value.available
    if (lost) {
      failures += 1
      recover = true
      const reason = result.ok ? result.value.reason : failureText(result)
      if (last === undefined) {
        // Nothing known yet: say exactly what the read said.
        yield result.ok ? { ok: true, value: { ...result.value, connection: 'reconnecting' } } : result
      } else {
        last = { ...last, connection: 'reconnecting', stale: true, staleSince: last.staleSince ?? new Date(now()).toISOString(), ...(reason === undefined ? {} : { staleReason: reason }) }
        yield { ok: true, value: last }
      }
      await sleep(backoff(failures, options.maxBackoffMs), signal)
      continue
    }
    failures = 0
    recover = false
    const view = result.value
    last = { ...view, connection: view.terminal ? 'ended' : 'live' }
    yield { ok: true, value: last }
    if (view.terminal) return
    const elapsed = now() - started
    if (elapsed < minIntervalMs) await sleep(minIntervalMs - elapsed, signal)
  }
}

/**
 * Poll one read on a fixed interval. A failed read after a success keeps the
 * last value, marked stale with the failure reason; a failure before any
 * success is yielded as is, so the view shows the reason instead of a blank.
 */
export async function* pollResource<V extends { available: boolean; reason?: string }>(read: () => Promise<RemoteResult<V>>, signal: AbortSignal, intervalMs: number, options: Pick<FollowOptions, 'sleep' | 'now' | 'maxBackoffMs'> = {}): AsyncIterable<RemoteResult<V & Freshness>> {
  const sleep = options.sleep ?? wait
  const now = options.now ?? Date.now
  let last: (V & Freshness) | undefined
  let failures = 0
  while (!signal.aborted) {
    const result = await read()
    if (signal.aborted) return
    const lost = !result.ok || !result.value.available
    if (lost && last !== undefined) {
      failures += 1
      const reason = result.ok ? result.value.reason : failureText(result)
      last = { ...last, stale: true, staleSince: last.staleSince ?? new Date(now()).toISOString(), ...(reason === undefined ? {} : { staleReason: reason }) }
      yield { ok: true, value: last }
      await sleep(backoff(failures, options.maxBackoffMs), signal)
      continue
    }
    if (lost) {
      failures += 1
      yield result as RemoteResult<V & Freshness>
      await sleep(backoff(failures, options.maxBackoffMs), signal)
      continue
    }
    failures = 0
    last = result.ok ? { ...result.value } : last
    yield { ok: true, value: last! }
    await sleep(intervalMs, signal)
  }
}
