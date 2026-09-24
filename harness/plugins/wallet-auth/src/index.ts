import { Service } from '@deepseek-ai/cordis'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import {
  AUTH_SERVICE_UNAVAILABLE,
  NONCE_BYTES,
  NONCE_STORE_UNAVAILABLE,
  NONCE_TTL_SECONDS,
  RATE_LIMIT_LIMIT,
  RATE_LIMIT_WINDOW_SECONDS,
  SIGNATURE_MAX_LENGTH,
  SIGNATURE_MIN_LENGTH,
  SIGNER_RECOVERY_MISSING,
  SIGNER_RECOVERY_UNAVAILABLE,
  WALLET_NONCE_EXPIRED,
  WALLET_SIGNATURE_INVALID,
  buildSiweMessage,
  compareRecoveredSigner,
  evaluateRateLimit,
  normalizeChainId,
  normalizeWalletAddress,
  normalizeWalletProvider,
  nonceStoreKey,
  parseSiteOrigin,
  rateLimitApplies,
  rateLimitClient,
  rateLimitKey,
  refuse,
  walletSignupIdentity,
  type WalletClientIdentity,
  type WalletProvider,
  type WalletRateLimitAction,
  type WalletRefusal,
  type WalletResult,
  type WalletSignupIdentity,
} from './policy.ts'

export * from './policy.ts'

export interface Config {
  /**
   * The origin the EIP-4361 message binds (the classic `SITE_URL`). Empty means
   * the nonce step refuses: the domain binding IS the anti-phishing property, so
   * an unconfigured deployment must not be able to issue a message.
   */
  siteUrl?: string
  /** Mirrors the classic `APP_ENV`; the rate limit applies in production only. */
  appEnvironment?: string
}

export const Config: z<Config> = z.object({
  siteUrl: z.string().default(''),
  appEnvironment: z.string().default('development'),
})

export interface WalletNonceRequest {
  address: string
  chainId?: number
  /** Resolved by the HTTP/Remote edge and used only for the rate-limit fingerprint. */
  client?: WalletClientIdentity
}

export interface IssuedWalletNonce {
  address: string
  chainId: number
  nonce: string
  /**
   * The full EIP-4361 message, already stored server-side. It is returned so the
   * user can read what they are about to sign; the verify step never reads it
   * back from the client.
   */
  message: string
  expiresInSeconds: number
}

/**
 * The verify payload, and nothing else.
 *
 * There is deliberately no `message` field: the signed message is the one the
 * server stored under `pg:auth:wallet:<address>`, so a client cannot re-bind the
 * host, URI, chain id, statement or nonce. An extra property on a request object
 * is ignored, never consulted.
 */
export interface WalletVerifyRequest {
  address: string
  signature: string
  wallet?: string
  /** Resolved by the HTTP/Remote edge and used only for the rate-limit fingerprint. */
  client?: WalletClientIdentity
}

export interface VerifiedWalletSigner {
  address: string
  wallet: WalletProvider
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgWalletAuth: WalletAuthService
  }
}

/**
 * PureGamma wallet sign-in seam (classic SIWE / EIP-4361).
 *
 * This is the Harness owner of `apps/api/routers/wallet_auth.py`. It issues the
 * single-use nonce message and verifies it; it does not create users, does not
 * write sessions and does not set cookies — the identity layer does that, using
 * `signupIdentity` for the first sign-in so the synthetic mailbox is derived in
 * exactly one place.
 *
 * Every method returns an explicit refusal (`ok: false` with a reason code) for
 * an unsupported, unconfigured or unverifiable request. No method returns a
 * default success.
 */
export abstract class WalletAuthService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgWalletAuth')
  }

  /** Issue and SERVER-SIDE store the single-use EIP-4361 message for an address. */
  abstract nonce(request: WalletNonceRequest): Promise<WalletResult<IssuedWalletNonce>>
  /** Consume the stored message and compare the recovered signer with the claimed address. */
  abstract verify(request: WalletVerifyRequest): Promise<WalletResult<VerifiedWalletSigner>>
  /** The placeholder identity a FIRST wallet sign-in creates (wallet sign-in is wallet sign-up). */
  abstract signupIdentity(address: string | null | undefined): WalletResult<WalletSignupIdentity>
}

/**
 * The single-use message store (Redis in the classic deployment).
 *
 * None of this is implemented here: a nonce store that cannot be reached in
 * production is an outage, not a licence to accept an unverifiable nonce.
 */
export interface WalletNonceStore {
  /** `SETEX`: the FULL message, keyed by address, expiring after `ttlSeconds`. */
  put(key: string, message: string, ttlSeconds: number): Promise<void>
  /** `GETDEL` (with a GET+DELETE fallback on older Redis): read once, then gone. */
  take(key: string): Promise<string | null>
  /** `INCR` + `EXPIRE` on the first increment of a window; returns the new count. */
  increment(key: string, windowSeconds: number): Promise<number>
}

/** secp256k1 / `eth_account` signer recovery — a provider-runtime capability. */
export interface WalletSignerRecovery {
  /** Recover the EIP-191 `personal_sign` signer of the STORED message, or throw. */
  recover(message: string, signature: string): Promise<string>
}

/** Provider-runtime capabilities, injected by the host at wiring time. */
export interface WalletAuthRuntime {
  nonceStore?: WalletNonceStore
  signerRecovery?: WalletSignerRecovery
}

interface PlatformRandom {
  getRandomValues(bytes: Uint8Array): Uint8Array
}

/**
 * 8 CSPRNG bytes as 16 hex characters — the classic `secrets.token_hex(8)`.
 *
 * Never `Math.random`: a guessable nonce makes every future signature
 * replayable. Returns null when no platform CSPRNG exists, and the caller then
 * refuses instead of falling back to a weaker source.
 */
function randomNonce(): string | null {
  const source = globalThis.crypto as PlatformRandom | undefined
  if (typeof source?.getRandomValues !== 'function') return null
  const bytes = new Uint8Array(NONCE_BYTES)
  source.getRandomValues(bytes)
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
}

/**
 * SIWE / EIP-4361 provider — an explicit migration and provider boundary.
 *
 * What this class does NOT do, on purpose:
 *
 * - **Signer recovery is a provider-runtime responsibility.** Recovering the
 *   address behind a `personal_sign` signature needs secp256k1 (`eth_account` in
 *   the classic handler). This provider takes a `WalletSignerRecovery` and never
 *   guesses: with none installed, `verify` refuses with
 *   SIGNER_RECOVERY_UNAVAILABLE instead of accepting a signature it cannot check.
 * - **The single-use nonce store is a provider-runtime responsibility.** It is a
 *   `WalletNonceStore` (Redis GETDEL/SETEX in production). No in-memory fallback
 *   is offered here, because an in-process store would silently accept a nonce
 *   that another process issued.
 * - **No wallet signature is ever accepted without the stored server-side
 *   message.** `verify` reads the message back from the store with `take`
 *   (single-use, before recovery, so a failed attempt burns the nonce) and hands
 *   that string to recovery. A caller-supplied message is not part of the
 *   contract and is never read.
 * - **It fails closed.** A missing nonce store, a store that throws, an
 *   unusable rate-limit counter, an unconfigured `siteUrl`, an absent CSPRNG or
 *   an absent signer recovery all refuse — the classic answered 503 there rather
 *   than accepting an unverifiable nonce.
 *
 * Client-visible failures use the classic reason codes (WALLET_NONCE_EXPIRED,
 * WALLET_SIGNATURE_INVALID, WALLET_SIGNATURE_MISMATCH, UNSUPPORTED_WALLET,
 * INVALID_WALLET_ADDRESS, RATE_LIMITED).
 */
export class SiweWalletAuthProvider extends WalletAuthService {
  static Config = Config

  private readonly siteUrl: string
  private readonly appEnvironment: string

  constructor(
    ctx: Context,
    config: Config = {},
    private readonly runtime: WalletAuthRuntime = {},
  ) {
    super(ctx)
    this.siteUrl = config.siteUrl ?? process.env.SITE_URL ?? ''
    this.appEnvironment = config.appEnvironment ?? process.env.APP_ENV ?? 'development'
  }

  signupIdentity(address: string | null | undefined): WalletResult<WalletSignupIdentity> {
    return walletSignupIdentity(address)
  }

  async nonce(request: WalletNonceRequest): Promise<WalletResult<IssuedWalletNonce>> {
    const address = normalizeWalletAddress(request.address)
    if (!address.ok) return address

    const chainId = normalizeChainId(request.chainId)
    if (!chainId.ok) return chainId

    const limited = await this.guardRateLimit(address.value, 'nonce', request.client)
    if (limited !== undefined) return limited

    const origin = parseSiteOrigin(this.siteUrl)
    if (!origin.ok) return origin

    const store = this.runtime.nonceStore
    if (store === undefined) return refuse(AUTH_SERVICE_UNAVAILABLE, NONCE_STORE_UNAVAILABLE)

    const nonce = randomNonce()
    if (nonce === null) return refuse(AUTH_SERVICE_UNAVAILABLE, 'no platform CSPRNG is available for the nonce')

    const message = buildSiweMessage({
      host: origin.value.host,
      origin: origin.value.origin,
      address: address.value,
      chainId: chainId.value,
      nonce,
      issuedAt: new Date().toISOString(),
    })
    try {
      await store.put(nonceStoreKey(address.value), message, NONCE_TTL_SECONDS)
    } catch {
      return refuse(AUTH_SERVICE_UNAVAILABLE, NONCE_STORE_UNAVAILABLE)
    }
    return {
      ok: true,
      value: {
        address: address.value,
        chainId: chainId.value,
        nonce,
        message,
        expiresInSeconds: NONCE_TTL_SECONDS,
      },
    }
  }

  async verify(request: WalletVerifyRequest): Promise<WalletResult<VerifiedWalletSigner>> {
    const address = normalizeWalletAddress(request.address)
    if (!address.ok) return address

    // The classic validates these bounds in pydantic, before the handler runs.
    const signature = (request.signature ?? '').trim()
    if (signature.length < SIGNATURE_MIN_LENGTH || signature.length > SIGNATURE_MAX_LENGTH) {
      return refuse(WALLET_SIGNATURE_INVALID, 'signature is not a plausible EVM signature')
    }

    const limited = await this.guardRateLimit(address.value, 'verify', request.client)
    if (limited !== undefined) return limited

    const wallet = normalizeWalletProvider(request.wallet)
    if (!wallet.ok) return wallet

    const store = this.runtime.nonceStore
    if (store === undefined) return refuse(AUTH_SERVICE_UNAVAILABLE, NONCE_STORE_UNAVAILABLE)

    // Single-use, and consumed BEFORE recovery: the classic reads the message out
    // of the store with GETDEL, so a failed signature cannot leave it replayable.
    let stored: string | null
    try {
      stored = await store.take(nonceStoreKey(address.value))
    } catch {
      return refuse(AUTH_SERVICE_UNAVAILABLE, NONCE_STORE_UNAVAILABLE)
    }
    if (stored === null || stored.trim().length === 0) {
      return refuse(WALLET_NONCE_EXPIRED, 'no stored message for this address; request a new nonce')
    }

    const recovery = this.runtime.signerRecovery
    if (recovery === undefined) return refuse(SIGNER_RECOVERY_UNAVAILABLE, SIGNER_RECOVERY_MISSING)

    // The STORED message, never a client-supplied one.
    let recovered: string
    try {
      recovered = await recovery.recover(stored, signature)
    } catch {
      return refuse(WALLET_SIGNATURE_INVALID, 'the signature could not be recovered against the stored message')
    }

    const comparison = compareRecoveredSigner(address.value, recovered)
    if (!comparison.ok) return comparison
    return { ok: true, value: { address: comparison.value, wallet: wallet.value } }
  }

  /**
   * The classic `_rate_limit`, which applies in production only.
   *
   * Returns the refusal, or undefined when the caller may proceed. A counter we
   * cannot read is a refusal, never a silent allowance.
   */
  private async guardRateLimit(
    address: string,
    action: WalletRateLimitAction,
    client: WalletClientIdentity | undefined,
  ): Promise<WalletRefusal | undefined> {
    if (!rateLimitApplies(this.appEnvironment)) return undefined
    const store = this.runtime.nonceStore
    if (store === undefined) return refuse(AUTH_SERVICE_UNAVAILABLE, NONCE_STORE_UNAVAILABLE)
    let count: number
    try {
      count = await store.increment(rateLimitKey(rateLimitClient(client), address, action), RATE_LIMIT_WINDOW_SECONDS)
    } catch {
      return refuse(AUTH_SERVICE_UNAVAILABLE, 'wallet rate limit counter unavailable')
    }
    const decision = evaluateRateLimit(count, RATE_LIMIT_LIMIT)
    return decision.ok ? undefined : decision
  }
}

export default SiweWalletAuthProvider
