/**
 * JEV advisory compatibility at the PureGamma/Rust boundary.
 *
 * This is a read-only validator, NOT a TypeSafe transport, signal generator,
 * risk decision, execution approval or order dispatcher. It mirrors the
 * pg-strategy jev_advisory.rs contract at the pinned PG-TSY revision.
 * Nanosecond u64 values MUST cross JSON as canonical decimal strings: JS
 * Number cannot losslessly represent real epoch nanoseconds.
 */
export const JEV_MODEL = 'jev-1.13.0'
export const JEV_INSTRUMENT = 'BINANCE_PM:BTCUSDC'
export const JEV_MAX_TTL_NS = 5_000_000_000n
const MAX_U64 = 18_446_744_073_709_551_615n

export type JevChoice = 'up' | 'down' | 'neutral'
export type JevAdvisoryResult = 'advice-agrees' | 'hold-new-exposure' | 'reduction-independent'

export interface JevAdvisoryObservation {
  instrument: typeof JEV_INSTRUMENT
  model: typeof JEV_MODEL
  source_event_ns: string
  received_ns: string
  expires_ns: string
  choice: JevChoice
  probabilities: Record<JevChoice, number>
  provider_confidence: number
  input_tokens: number
  output_tokens: number
}

/** Identity of an independently produced, deterministic policy signal. */
export interface JevSignalIdentity {
  venue: string
  instrument: string
  score: number
  source_event_ns: string
  created_at_ns: string
  expires_at_ns: string
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined
}

function nanoseconds(value: unknown): bigint | undefined {
  if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)) return undefined
  const parsed = BigInt(value)
  return parsed <= MAX_U64 ? parsed : undefined
}

function probability(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
}

function tokens(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

/**
 * Validate an already-normalized observation. This function performs NO HTTP
 * and does not convert JS numbers into timestamps: a lossy parse must fail.
 */
export function validateJevObservation(input: unknown, nowNs: string): JevAdvisoryObservation | undefined {
  const now = nanoseconds(nowNs)
  const data = record(input)
  if (now === undefined || !data || data.instrument !== JEV_INSTRUMENT || data.model !== JEV_MODEL) return undefined
  const source = nanoseconds(data.source_event_ns)
  const received = nanoseconds(data.received_ns)
  const expires = nanoseconds(data.expires_ns)
  if (source === undefined || received === undefined || expires === undefined || source === 0n
    || source > received || received > now || now >= expires || expires <= source
    || expires - source > JEV_MAX_TTL_NS) return undefined
  const choice = data.choice
  if (choice !== 'up' && choice !== 'down' && choice !== 'neutral') return undefined
  const probabilities = record(data.probabilities)
  if (!probabilities || Object.keys(probabilities).length !== 3
    || !probability(probabilities.up) || !probability(probabilities.down)
    || !probability(probabilities.neutral)) return undefined
  const total = probabilities.up + probabilities.down + probabilities.neutral
  const highest = Math.max(probabilities.up, probabilities.down, probabilities.neutral)
  if (Math.abs(total - 1) > 0.001 || probabilities[choice] < highest - 0.001
    || !probability(data.provider_confidence)
    || !tokens(data.input_tokens) || !tokens(data.output_tokens)) return undefined
  return {
    instrument: JEV_INSTRUMENT,
    model: JEV_MODEL,
    source_event_ns: source.toString(),
    received_ns: received.toString(),
    expires_ns: expires.toString(),
    choice,
    probabilities: { up: probabilities.up, down: probabilities.down, neutral: probabilities.neutral },
    provider_confidence: data.provider_confidence,
    input_tokens: data.input_tokens,
    output_tokens: data.output_tokens,
  }
}

/** Advisory comparison ONLY. 'advice-agrees' is not permission to trade. */
export function compareJevWithSignal(
  observation: unknown,
  signal: JevSignalIdentity,
  effect: 'increase' | 'reduce-only',
  nowNs: string,
): JevAdvisoryResult {
  // Model outage must never block a separately risk-authorized owned reduction.
  if (effect === 'reduce-only') return 'reduction-independent'
  const validated = validateJevObservation(observation, nowNs)
  const now = nanoseconds(nowNs)
  const source = nanoseconds(signal.source_event_ns)
  const created = nanoseconds(signal.created_at_ns)
  const expires = nanoseconds(signal.expires_at_ns)
  if (!validated || now === undefined || source === undefined || created === undefined || expires === undefined
    || signal.venue !== 'BINANCE_PM' || signal.instrument !== 'BTCUSDC'
    || source !== BigInt(validated.source_event_ns) || created < source || expires <= now
    || !Number.isFinite(signal.score)) return 'hold-new-exposure'
  if ((validated.choice === 'up' && signal.score > 0)
    || (validated.choice === 'down' && signal.score < 0)) return 'advice-agrees'
  return 'hold-new-exposure'
}
