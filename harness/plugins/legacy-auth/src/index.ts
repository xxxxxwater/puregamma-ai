import { readFileSync, statSync } from 'node:fs'
import process from 'node:process'

/**
 * Where a legacy-api provider gets the bearer it sends to FastAPI.
 *
 * - `authTokenEnv` (default `PUREGAMMA_LEGACY_API_TOKEN`): one token for the
 *   whole Host. Only correct for the single-operator Web host.
 * - `authTokenFile`: a file holding one user-scoped token. The session broker
 *   writes it for the one user a Host serves and rewrites it before expiry, so
 *   the file is read per request behind a short cache and Hosts never restart
 *   to rotate. When `authTokenFile` is set the env token is never consulted:
 *   a missing, unreadable, group/world-readable or malformed file yields no
 *   bearer (the provider fails the call) rather than a shared credential.
 */
export interface BearerSourceConfig {
  authTokenEnv?: string
  authTokenFile?: string
  authTokenCacheMs?: number
}

export const DEFAULT_TOKEN_ENV = 'PUREGAMMA_LEGACY_API_TOKEN'
export const DEFAULT_TOKEN_CACHE_MS = 5000
const MAX_TOKEN_LENGTH = 8192
// JWT/opaque bearer alphabet; anything else (spaces, newlines inside, control
// characters) could smuggle a header and is refused.
const TOKEN_SHAPE = /^[A-Za-z0-9._~+/=-]+$/

export type BearerSource = (() => string | undefined) & { readonly description: string }

export function createBearerSource(config: BearerSourceConfig = {}, now: () => number = Date.now): BearerSource {
  const file = config.authTokenFile?.trim()
  if (!file) {
    const env = config.authTokenEnv ?? DEFAULT_TOKEN_ENV
    return Object.assign(() => process.env[env] || undefined, { description: env })
  }
  const cacheMs = Math.min(60000, Math.max(0, config.authTokenCacheMs ?? DEFAULT_TOKEN_CACHE_MS))
  let cached: { value: string | undefined; at: number } | undefined
  const read = (): string | undefined => {
    try {
      const stat = statSync(file)
      if (!stat.isFile()) return undefined
      // The token is one user's credential: refuse a file others can read.
      if (process.platform !== 'win32' && (stat.mode & 0o077) !== 0) return undefined
      const value = readFileSync(file, 'utf8').trim()
      if (!value || value.length > MAX_TOKEN_LENGTH || !TOKEN_SHAPE.test(value)) return undefined
      return value
    } catch {
      return undefined
    }
  }
  return Object.assign(() => {
    const at = now()
    if (!cached || at - cached.at >= cacheMs) cached = { value: read(), at }
    return cached.value
  }, { description: `authTokenFile ${file}` })
}
