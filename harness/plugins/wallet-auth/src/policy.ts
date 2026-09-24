/**
 * Pure, fail-closed policy for classic SIWE / EIP-4361 wallet sign-in.
 *
 * This module owns the behaviour of `apps/api/routers/wallet_auth.py`: it
 * decides, and the provider in `index.ts` performs. It holds no session, no
 * database handle, no Redis client and imports nothing at all.
 *
 * Four invariants are ported from the classic handler, and none is negotiable:
 *
 * 1. **The message is server-side.** The nonce step builds the FULL EIP-4361
 *    message (host, statement, URI, chain id, nonce, issued-at) and stores it
 *    under `pg:auth:wallet:<address>`; the verify step reads it back
 *    single-use. The client never hands the message back, so it cannot re-bind
 *    the domain, the chain, the statement or the nonce. The verify request type
 *    in `index.ts` therefore has no `message` field, and the signer recovery
 *    step is handed the STORED string and nothing else.
 * 2. **A signature only means something against a stored message.** Signer
 *    recovery (secp256k1 / eth_account) is a provider-runtime capability that
 *    cannot be faked here, so this module exposes `compareRecoveredSigner`
 *    for an already-recovered signer and refuses every unavailable path
 *    (`SIGNER_RECOVERY_UNAVAILABLE`) instead of pretending to authenticate.
 * 3. **Unverifiable ⇒ refuse.** A missing nonce store, an unusable counter, an
 *    unconfigured site URL or an unsupported wallet yields an explicit refusal
 *    code. Nothing here returns a default success, a zero or an empty
 *    collection.
 * 4. **Addresses are compared lowercased, never coerced.** 0x + exactly 40 hex
 *    characters or nothing.
 *
 * EIP-55 needs Keccak-256 and the rate-limit fingerprint needs SHA-256. The
 * fingerprint comes from `node:crypto`; Keccak-256 is the one thing no stdlib
 * provides (OpenSSL exposes only NIST SHA-3, which pads differently), so it is
 * implemented from FIPS-202 and pinned to the canonical EIP-55 vectors in
 * `harness/scripts/wallet-auth.test.mjs`. This module still holds no session,
 * database handle, Redis client or Cordis service.
 */

import { createHash } from 'node:crypto'

// ------------------------------------------------------------------ addresses

/** The classic `_ADDRESS_RE`: exactly 0x + 40 hex characters. */
export const ADDRESS_PATTERN = /^0x[0-9a-fA-F]{40}$/

// ------------------------------------------------------------------- wallets

/** The classic `_WALLET_PROVIDERS`. */
export const SUPPORTED_WALLETS = ['metamask', 'zerion', 'injected'] as const

export type WalletProvider = (typeof SUPPORTED_WALLETS)[number]

/** The classic pydantic default for an omitted `wallet` field. */
export const DEFAULT_WALLET: WalletProvider = 'injected'

/** Classic `UserIdentity.provider` for a wallet identity. */
export const WALLET_IDENTITY_PROVIDER = 'evm_wallet'
/** Classic `User.auth_provider` for a wallet account. */
export const WALLET_AUTH_PROVIDER = 'wallet'

// --------------------------------------------------------------------- nonces

/** Classic `_NONCE_TTL_SECONDS`: the stored message is single-use and 5 minutes old at most. */
export const NONCE_TTL_SECONDS = 300
/** `secrets.token_hex(8)` ⇒ 8 random bytes, rendered as 16 hex characters. */
export const NONCE_BYTES = 8
export const NONCE_HEX_LENGTH = NONCE_BYTES * 2
/** Classic `_nonce_key`: one stored message per address. */
export const NONCE_KEY_PREFIX = 'pg:auth:wallet:'

// ------------------------------------------------------------------ rate limit

/** Classic `_rate_limit(..., limit=10, window=600)` on both routes, production only. */
export const RATE_LIMIT_LIMIT = 10
export const RATE_LIMIT_WINDOW_SECONDS = 600
export const RATE_LIMIT_KEY_PREFIX = 'pg:auth:wallet:rl:'

export type WalletRateLimitAction = 'nonce' | 'verify'

/** The classic request fields the rate-limit fingerprint is built from. */
export interface WalletClientIdentity {
  /** `x-real-ip`. */
  realIp?: string | null
  /** `x-forwarded-for`; only the first entry is used. */
  forwardedFor?: string | null
  /** The peer address, used when no forwarding header is present. */
  peer?: string | null
}

// -------------------------------------------------------------------- messages

export const DEFAULT_CHAIN_ID = 1
export const SIWE_VERSION = '1'

/** The exact statement sentence from the classic `_build_message`. */
export const SIWE_STATEMENT = 'Sign in to PureGamma AI with your wallet. This request will not trigger a blockchain transaction or cost any gas fees.'

/** Classic `_PLACEHOLDER_EMAIL_DOMAIN`. */
export const PLACEHOLDER_EMAIL_DOMAIN = 'wallet.puregamma.local'

/** Classic pydantic bounds on `signature`. */
export const SIGNATURE_MIN_LENGTH = 10
export const SIGNATURE_MAX_LENGTH = 256

// ------------------------------------------------------- refusal vocabulary

export const INVALID_WALLET_ADDRESS = 'INVALID_WALLET_ADDRESS'
export const UNSUPPORTED_WALLET = 'UNSUPPORTED_WALLET'
export const INVALID_CHAIN_ID = 'INVALID_CHAIN_ID'
export const RATE_LIMITED = 'RATE_LIMITED'
export const WALLET_NONCE_EXPIRED = 'WALLET_NONCE_EXPIRED'
export const WALLET_SIGNATURE_INVALID = 'WALLET_SIGNATURE_INVALID'
export const WALLET_SIGNATURE_MISMATCH = 'WALLET_SIGNATURE_MISMATCH'
/** The classic 503 "Authentication service unavailable": Redis down, counter unusable, nothing configured. */
export const AUTH_SERVICE_UNAVAILABLE = 'AUTH_SERVICE_UNAVAILABLE'
/** This port only: recovery is a provider-runtime capability and is not installed. */
export const SIGNER_RECOVERY_UNAVAILABLE = 'SIGNER_RECOVERY_UNAVAILABLE'

export type WalletAuthFailureCode =
  | typeof INVALID_WALLET_ADDRESS
  | typeof UNSUPPORTED_WALLET
  | typeof INVALID_CHAIN_ID
  | typeof RATE_LIMITED
  | typeof WALLET_NONCE_EXPIRED
  | typeof WALLET_SIGNATURE_INVALID
  | typeof WALLET_SIGNATURE_MISMATCH
  | typeof AUTH_SERVICE_UNAVAILABLE
  | typeof SIGNER_RECOVERY_UNAVAILABLE

export const NONCE_STORE_UNAVAILABLE = 'wallet nonce store unavailable'
export const RATE_LIMIT_COUNTER_UNAVAILABLE = 'wallet rate limit counter unavailable; refusing rather than allowing an unenforced request'
export const SITE_URL_MISSING = 'SITE_URL is not configured; refusing to bind a SIWE message to an unknown host'
export const SIGNER_RECOVERY_MISSING = 'signer recovery is not configured; refusing to accept an unverifiable signature'
export const SIGNER_NOT_RECOVERED = 'no signer was recovered from the stored message'

export interface WalletSuccess<T> {
  ok: true
  value: T
}

export interface WalletRefusal {
  ok: false
  code: WalletAuthFailureCode
  reason: string
}

export type WalletResult<T> = WalletSuccess<T> | WalletRefusal

export function refuse(code: WalletAuthFailureCode, reason: string): WalletRefusal {
  return { ok: false, code, reason }
}

// ------------------------------------------------------------------- addresses

/**
 * Normalize a wallet address the way the classic handler does: trim, lowercase,
 * then match 0x + 40 hex. Anything else — a missing 0x, 41 or 39 characters, a
 * non-hex character, a trailing space inside the payload — is refused with
 * INVALID_WALLET_ADDRESS. It is never coerced, truncated or padded, and a
 * caller-supplied checksummed form is accepted because it is lowercased first.
 */
export function normalizeWalletAddress(value: string | null | undefined): WalletResult<string> {
  const address = (value ?? '').trim().toLowerCase()
  if (!ADDRESS_PATTERN.test(address)) {
    return refuse(INVALID_WALLET_ADDRESS, 'wallet address must be 0x followed by 40 hex characters')
  }
  return { ok: true, value: address }
}

/**
 * Normalize the wallet label.
 *
 * Empty (absent, or whitespace only) means the classic default `injected`;
 * the classic itself trims and would refuse a whitespace-only label, which is
 * the only deliberate divergence here — a label the client omitted already
 * defaults, and the label is cosmetic (it never selects which signature is
 * accepted), so resolving it to the default cannot widen anything. Any other
 * unsupported value is refused with the classic UNSUPPORTED_WALLET.
 */
export function normalizeWalletProvider(value: string | null | undefined): WalletResult<WalletProvider> {
  const wallet = (value ?? '').trim().toLowerCase()
  if (wallet.length === 0) return { ok: true, value: DEFAULT_WALLET }
  if ((SUPPORTED_WALLETS as readonly string[]).includes(wallet)) return { ok: true, value: wallet as WalletProvider }
  return refuse(UNSUPPORTED_WALLET, `wallet provider must be one of ${SUPPORTED_WALLETS.join(', ')}`)
}

/** The classic validates `chain_id: int = Field(default=1, ge=1)` before building the message. */
export function normalizeChainId(value: number | null | undefined): WalletResult<number> {
  if (value === null || value === undefined) return { ok: true, value: DEFAULT_CHAIN_ID }
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 1) {
    return refuse(INVALID_CHAIN_ID, 'chain id must be an integer >= 1')
  }
  return { ok: true, value }
}

// ---------------------------------------------------------------- EIP-55 / hashes

const KECCAK_MASK = (1n << 64n) - 1n
const KECCAK_RATE_BYTES = 136
const KECCAK_ROUNDS = 24
/** r[x][y] flattened as x + 5y. */
const KECCAK_ROTATION = [
  0, 1, 62, 28, 27,
  36, 44, 6, 55, 20,
  3, 10, 43, 25, 39,
  41, 45, 15, 21, 8,
  18, 2, 61, 56, 14,
]
const KECCAK_ROUND_CONSTANTS = [
  0x0000000000000001n, 0x0000000000008082n, 0x800000000000808an, 0x8000000080008000n,
  0x000000000000808bn, 0x0000000080000001n, 0x8000000080008081n, 0x8000000000008009n,
  0x000000000000008an, 0x0000000000000088n, 0x0000000080008009n, 0x000000008000000an,
  0x000000008000808bn, 0x800000000000008bn, 0x8000000000008089n, 0x8000000000008003n,
  0x8000000000008002n, 0x8000000000000080n, 0x000000000000800an, 0x800000008000000an,
  0x8000000080008081n, 0x8000000000008080n, 0x0000000080000001n, 0x8000000080008008n,
]

function rotateLeft64(lane: bigint, shift: number): bigint {
  const by = BigInt(shift)
  return ((lane << by) | (lane >> (64n - by))) & KECCAK_MASK
}

function keccakF1600(state: bigint[]): void {
  for (let round = 0; round < KECCAK_ROUNDS; round++) {
    // theta
    const column: bigint[] = []
    for (let x = 0; x < 5; x++) column[x] = state[x]! ^ state[x + 5]! ^ state[x + 10]! ^ state[x + 15]! ^ state[x + 20]!
    for (let x = 0; x < 5; x++) {
      const delta = column[(x + 4) % 5]! ^ rotateLeft64(column[(x + 1) % 5]!, 1)
      for (let y = 0; y < 5; y++) state[x + 5 * y] = state[x + 5 * y]! ^ delta
    }
    // rho + pi
    const shuffled: bigint[] = new Array<bigint>(25).fill(0n)
    for (let x = 0; x < 5; x++) {
      for (let y = 0; y < 5; y++) {
        const lane = x + 5 * y
        shuffled[y + 5 * ((2 * x + 3 * y) % 5)] = rotateLeft64(state[lane]!, KECCAK_ROTATION[lane]!)
      }
    }
    // chi
    for (let x = 0; x < 5; x++) {
      for (let y = 0; y < 5; y++) {
        const lane = x + 5 * y
        state[lane] = shuffled[lane]! ^ (~shuffled[(x + 1) % 5 + 5 * y]! & KECCAK_MASK & shuffled[(x + 2) % 5 + 5 * y]!)
      }
    }
    // iota
    state[0] = state[0]! ^ KECCAK_ROUND_CONSTANTS[round]!
  }
}

function utf8Bytes(text: string): Uint8Array {
  return new TextEncoder().encode(text)
}

/** Keccak-256 (the pre-SHA3 padding ethereum uses), returned as 32 bytes. */
function keccak256(input: Uint8Array): Uint8Array {
  const state: bigint[] = new Array<bigint>(25).fill(0n)
  const padded = new Uint8Array(Math.ceil((input.length + 1) / KECCAK_RATE_BYTES) * KECCAK_RATE_BYTES)
  padded.set(input)
  padded[input.length] = 0x01
  padded[padded.length - 1] = padded[padded.length - 1]! | 0x80
  for (let offset = 0; offset < padded.length; offset += KECCAK_RATE_BYTES) {
    for (let lane = 0; lane < KECCAK_RATE_BYTES / 8; lane++) {
      let value = 0n
      for (let byte = 7; byte >= 0; byte--) value = (value << 8n) | BigInt(padded[offset + lane * 8 + byte]!)
      state[lane] = state[lane]! ^ value
    }
    keccakF1600(state)
  }
  const digest = new Uint8Array(32)
  for (let lane = 0; lane < 4; lane++) {
    let value = state[lane]!
    for (let byte = 0; byte < 8; byte++) {
      digest[lane * 8 + byte] = Number(value & 0xffn)
      value >>= 8n
    }
  }
  return digest
}

/**
 * EIP-55 checksummed rendering of a valid address.
 *
 * This is the dependency-free stand-in for `eth_utils.to_checksum_address`,
 * which the classic imports inside `_build_message`. Keccak-256 over the
 * lowercase hex body decides the case of every a-f nibble, so the address line
 * the user signs is identical to the classic message. Validated against
 * eth_utils output in the test file.
 */
export function toChecksumAddress(address: string): string {
  const lower = address.trim().toLowerCase()
  if (!ADDRESS_PATTERN.test(lower)) return address
  const body = lower.slice(2)
  const digest = keccak256(utf8Bytes(body))
  let checksummed = '0x'
  for (let index = 0; index < body.length; index++) {
    const character = body[index]!
    const nibble = index % 2 === 0 ? digest[index >> 1]! >> 4 : digest[index >> 1]! & 0x0f
    checksummed += nibble >= 8 ? character.toUpperCase() : character
  }
  return checksummed
}

/**
 * SHA-256 of a UTF-8 string, hex encoded — identical to Python `hashlib.sha256`.
 *
 * The platform already provides this (`node:crypto` is FIPS SHA-256), so it is not
 * hand-rolled here. Keccak-256 above has no stdlib equivalent — OpenSSL exposes
 * only NIST SHA-3, which pads differently — which is why that one is implemented
 * and pinned to the canonical EIP-55 vectors in the test file.
 */
function sha256Hex(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex')
}

// ------------------------------------------------------------- site origin

export interface SiteOrigin {
  /** The classic `parsed.netloc`: host, with the port when one is given. */
  host: string
  origin: string
}

/**
 * Port of the classic `_site_origin`: a bare host is assumed to be https.
 *
 * A missing or unparseable SITE_URL is refused rather than defaulted. The
 * classic falls back to a `localhost` development default; here an unconfigured
 * deployment must not be able to produce a message whose host line is a lie the
 * user would then sign, so the nonce step fails closed instead.
 */
export function parseSiteOrigin(siteUrl: string | null | undefined): WalletResult<SiteOrigin> {
  const raw = (siteUrl ?? '').trim()
  if (raw.length === 0) return refuse(AUTH_SERVICE_UNAVAILABLE, SITE_URL_MISSING)
  let parsed: URL
  try {
    parsed = new URL(raw.includes('://') ? raw : `https://${raw}`)
  } catch {
    return refuse(AUTH_SERVICE_UNAVAILABLE, `SITE_URL is not a valid URL: ${raw}`)
  }
  const host = parsed.host
  if (host.length === 0) return refuse(AUTH_SERVICE_UNAVAILABLE, `SITE_URL has no host: ${raw}`)
  const scheme = parsed.protocol.replace(/:$/, '') || 'https'
  return { ok: true, value: { host, origin: `${scheme}://${host}` } }
}

// ------------------------------------------------------------------ messages

export interface SiweMessageInput {
  host: string
  origin: string
  /** A normalized (lowercase) address from `normalizeWalletAddress`. */
  address: string
  chainId: number
  nonce: string
  /** ISO-8601 UTC instant; the classic uses `datetime.now(timezone.utc).isoformat()`. */
  issuedAt: string
}

/**
 * The classic `_build_message`, byte for byte.
 *
 * Ten lines in EIP-4361 order: the "<host> wants you to sign in with your
 * Ethereum account:" header, the checksummed address, a blank line, the exact
 * statement sentence, a blank line, then URI / Version / Chain ID / Nonce /
 * Issued At. No trailing newline.
 *
 * The address is checksummed exactly as `eth_utils.to_checksum_address` does
 * inside the classic (which falls back to the raw address if the import fails).
 * This is a formatter, not a validator: callers obtain host/origin from
 * `parseSiteOrigin` and the address from `normalizeWalletAddress` first.
 */
export function buildSiweMessage(input: SiweMessageInput): string {
  return [
    `${input.host} wants you to sign in with your Ethereum account:`,
    toChecksumAddress(input.address),
    '',
    SIWE_STATEMENT,
    '',
    `URI: ${input.origin}`,
    `Version: ${SIWE_VERSION}`,
    `Chain ID: ${input.chainId}`,
    `Nonce: ${input.nonce}`,
    `Issued At: ${input.issuedAt}`,
  ].join('\n')
}

// -------------------------------------------------------------------- nonces

/**
 * The Redis key the SERVER-SIDE message is stored under, single-use.
 *
 * The anti-tamper property of this whole flow lives here: the message is
 * written by the nonce step and read back by the verify step, and no request
 * field can carry it. Requires a normalized address; an unnormalized one makes
 * the key miss, which fails closed as WALLET_NONCE_EXPIRED.
 */
export function nonceStoreKey(address: string): string {
  return `${NONCE_KEY_PREFIX}${address}`
}

// ---------------------------------------------------------------- rate limiting

/**
 * Port of the classic client resolution: `x-real-ip` first, then the first
 * entry of `x-forwarded-for`, then the peer, then "unknown". A header present
 * but empty falls through, exactly like Python's `or`.
 */
export function rateLimitClient(client: WalletClientIdentity | null | undefined): string {
  const forwarded = (client?.realIp || client?.forwardedFor) ?? ''
  if (forwarded.length > 0) return forwarded.split(',')[0]!.trim()
  return (client?.peer || 'unknown').trim()
}

/** `sha256("<client>:<address>:<action>")`, hex — the classic `hashlib` digest. */
export function rateLimitFingerprint(client: string, address: string, action: WalletRateLimitAction): string {
  return sha256Hex(`${client}:${address}:${action}`)
}

export function rateLimitKey(client: string, address: string, action: WalletRateLimitAction): string {
  return `${RATE_LIMIT_KEY_PREFIX}${rateLimitFingerprint(client, address, action)}`
}

/**
 * The classic guard: `if settings.app_environment.lower() != "production": return`.
 *
 * The deployment contract that makes this safe is that APP_ENV is set to
 * `production` in production; an unset environment mirrors the classic and
 * does not rate limit.
 */
export function rateLimitApplies(environment: string | null | undefined): boolean {
  return (environment ?? '').trim().toLowerCase() === 'production'
}

export interface RateLimitAllowance {
  count: number
  limit: number
  remaining: number
}

export interface RateLimitRefusal extends WalletRefusal {
  code: typeof RATE_LIMITED
  retryAfterSeconds: number
}

/**
 * The classic `count > limit` decision, made fail-closed.
 *
 * Exactly `limit` is allowed (the classic only refuses on `>`). A counter we
 * cannot read, and a non-positive or non-integer limit, are refusals rather than
 * a free pass: a broken counter must deny, not open.
 */
export function evaluateRateLimit(
  count: number,
  limit: number = RATE_LIMIT_LIMIT,
  windowSeconds: number = RATE_LIMIT_WINDOW_SECONDS,
): WalletResult<RateLimitAllowance> {
  if (!Number.isInteger(limit) || limit <= 0) {
    return refuse(AUTH_SERVICE_UNAVAILABLE, `rate limit is misconfigured (${limit}); refusing to serve unenforced requests`)
  }
  if (!Number.isInteger(count) || count < 0) {
    return refuse(AUTH_SERVICE_UNAVAILABLE, RATE_LIMIT_COUNTER_UNAVAILABLE)
  }
  if (count > limit) {
    const denial: RateLimitRefusal = {
      ok: false,
      code: RATE_LIMITED,
      reason: `rate limit of ${limit} per ${windowSeconds}s exceeded`,
      retryAfterSeconds: windowSeconds,
    }
    return denial
  }
  return { ok: true, value: { count, limit, remaining: limit - count } }
}

// ------------------------------------------------------------- sign-up identity

export interface WalletSignupIdentity {
  address: string
  /** The synthetic mailbox that keeps the classic NOT NULL + unique email column honest. */
  email: string
  /** The classic `f"{address[:6]}...{address[-4:]}"`. */
  displayName: string
  authProvider: typeof WALLET_AUTH_PROVIDER
  identityProvider: typeof WALLET_IDENTITY_PROVIDER
}

/**
 * The identity a FIRST wallet sign-in creates — wallet sign-in IS wallet
 * sign-up in the classic handler, so the placeholder mailbox and the derived
 * display name are produced here and nowhere else. An invalid address is
 * refused instead of yielding a synthetic mailbox for a non-address.
 *
 * The caller (the identity/account layer, not this plugin) is what persists
 * this; the email is never used to contact anyone.
 */
export function walletSignupIdentity(address: string | null | undefined): WalletResult<WalletSignupIdentity> {
  const normalized = normalizeWalletAddress(address)
  if (!normalized.ok) return normalized
  const value = normalized.value
  return {
    ok: true,
    value: {
      address: value,
      email: `${value}@${PLACEHOLDER_EMAIL_DOMAIN}`,
      displayName: `${value.slice(0, 6)}...${value.slice(-4)}`,
      authProvider: WALLET_AUTH_PROVIDER,
      identityProvider: WALLET_IDENTITY_PROVIDER,
    },
  }
}

// ------------------------------------------------------------ signer comparison

/**
 * Compare the claimed address with the signer recovered from the STORED
 * message — the classic `Account.recover_message(...) != address` check.
 *
 * Recovery itself is deliberately NOT here: secp256k1 recovery needs
 * `eth_account`, and a pure module that cannot recover must not pretend to
 * authorize. `recovered === null` therefore means "recovery produced nothing"
 * and is refused as WALLET_SIGNATURE_INVALID, never treated as a match. Both
 * addresses must be valid EVM addresses; anything else is refused too.
 */
export function compareRecoveredSigner(
  claimed: string,
  recovered: string | null | undefined,
): WalletResult<string> {
  const expected = normalizeWalletAddress(claimed)
  if (!expected.ok) return expected
  if (recovered === null || recovered === undefined || recovered.trim().length === 0) {
    return refuse(WALLET_SIGNATURE_INVALID, SIGNER_NOT_RECOVERED)
  }
  const actual = normalizeWalletAddress(recovered)
  if (!actual.ok) return refuse(WALLET_SIGNATURE_INVALID, 'recovered signer is not an EVM address')
  if (actual.value !== expected.value) {
    return refuse(WALLET_SIGNATURE_MISMATCH, 'recovered signer does not match the claimed address')
  }
  return { ok: true, value: expected.value }
}
