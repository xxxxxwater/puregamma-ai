/**
 * Admission control for the broker: token buckets (rates) and counters
 * (concurrency). Everything is per key, so one user's flood only drains that
 * user's bucket; the only shared budget is the global Host start rate, and
 * it is spent only by requests that need a new Host.
 */

export class TokenBucket {
  private tokens: number
  private at: number

  constructor(
    readonly capacity: number,
    /** Tokens added per second. */
    readonly refillPerSec: number,
    private readonly now: () => number = Date.now,
  ) {
    this.tokens = capacity
    this.at = now()
  }

  private refill(): void {
    const at = this.now()
    this.tokens = Math.min(this.capacity, this.tokens + ((at - this.at) / 1000) * this.refillPerSec)
    this.at = at
  }

  /** Take one token; on refusal returns the seconds until one is available. */
  take(): { ok: true } | { ok: false; retryAfterSec: number } {
    this.refill()
    if (this.tokens >= 1) {
      this.tokens -= 1
      return { ok: true }
    }
    return { ok: false, retryAfterSec: Math.max(1, Math.ceil((1 - this.tokens) / this.refillPerSec)) }
  }

  /** True once the bucket has refilled completely (safe to forget). */
  full(): boolean {
    this.refill()
    return this.tokens >= this.capacity
  }
}

/** One bucket per key, with a bounded number of keys. */
export class KeyedBuckets {
  private readonly buckets = new Map<string, TokenBucket>()

  constructor(
    readonly capacity: number,
    readonly refillPerSec: number,
    private readonly maxKeys = 50_000,
    private readonly now: () => number = Date.now,
  ) {}

  take(key: string): { ok: true } | { ok: false; retryAfterSec: number } {
    let bucket = this.buckets.get(key)
    if (!bucket) {
      if (this.buckets.size >= this.maxKeys) this.prune()
      bucket = new TokenBucket(this.capacity, this.refillPerSec, this.now)
      this.buckets.set(key, bucket)
    }
    return bucket.take()
  }

  /** Drop buckets that are full again; if still too many, drop the oldest. */
  prune(): void {
    for (const [key, bucket] of this.buckets) if (bucket.full()) this.buckets.delete(key)
    while (this.buckets.size >= this.maxKeys) this.buckets.delete(this.buckets.keys().next().value!)
  }

  get size(): number { return this.buckets.size }
}

/** Per-key concurrency counter with a ceiling. */
export class Concurrency {
  private readonly counts = new Map<string, number>()

  constructor(readonly limit: number) {}

  /** Reserve a slot; the returned release is idempotent. */
  acquire(key: string): (() => void) | undefined {
    const current = this.counts.get(key) ?? 0
    if (current >= this.limit) return undefined
    this.counts.set(key, current + 1)
    let released = false
    return () => {
      if (released) return
      released = true
      const left = (this.counts.get(key) ?? 1) - 1
      if (left <= 0) this.counts.delete(key)
      else this.counts.set(key, left)
    }
  }

  count(key: string): number { return this.counts.get(key) ?? 0 }
}

/** Raised when admission is refused for rate or concurrency; maps to 429. */
export class RateLimited extends Error {
  constructor(readonly code: string, readonly retryAfterSec: number) {
    super(code)
  }
}
