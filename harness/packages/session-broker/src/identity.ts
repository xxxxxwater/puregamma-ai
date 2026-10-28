import { createHash } from 'node:crypto'
import type { IncomingHttpHeaders } from 'node:http'

/** The user's own PureGamma credential, exactly as FastAPI accepts it. */
export type UserCredential = { kind: 'bearer'; value: string } | { kind: 'cookie'; name: string; value: string }

export interface Identity {
  userId: string
  credential: UserCredential
}

export class ApiUnavailable extends Error {}

/** Parse a Cookie header without trusting duplicates: two values for one name is ambiguous and refused. */
export function readCookie(header: string | undefined, name: string): string | undefined | null {
  if (!header) return undefined
  let found: string | undefined
  for (const part of header.split(';')) {
    const index = part.indexOf('=')
    if (index < 0) continue
    if (part.slice(0, index).trim() !== name) continue
    if (found !== undefined) return null
    found = part.slice(index + 1).trim()
  }
  return found
}

export function credentialOf(headers: IncomingHttpHeaders, cookieName: string): UserCredential | undefined {
  const authorization = headers.authorization
  if (authorization) {
    const [scheme, value, extra] = authorization.split(' ')
    if (scheme?.toLowerCase() !== 'bearer' || !value || extra !== undefined) return undefined
    return { kind: 'bearer', value }
  }
  const value = readCookie(headers.cookie, cookieName)
  return value ? { kind: 'cookie', name: cookieName, value } : undefined
}

export function credentialHeaders(credential: UserCredential): Record<string, string> {
  return credential.kind === 'bearer'
    ? { authorization: `Bearer ${credential.value}` }
    : { cookie: `${credential.name}=${credential.value}` }
}

/**
 * Resolves a request credential to a PureGamma user through FastAPI `GET /me`.
 * Results are cached by a hash of the credential for a few seconds; a revoked
 * session therefore stops resolving within `cacheMs`. Unauthenticated answers
 * are cached too (shorter) so a flood of bad cookies does not fan out to FastAPI.
 */
export class Authenticator {
  private readonly cache = new Map<string, { userId: string | null; at: number }>()

  constructor(
    private readonly apiBaseUrl: string,
    private readonly cookieName: string,
    private readonly cacheMs: number,
    private readonly fetchImpl: typeof fetch = fetch,
    private readonly now: () => number = Date.now,
  ) {}

  async identify(headers: IncomingHttpHeaders): Promise<Identity | null> {
    const credential = credentialOf(headers, this.cookieName)
    if (!credential) return null
    const key = createHash('sha256').update(`${credential.kind}\0${credential.value}`).digest('base64url')
    const at = this.now()
    const hit = this.cache.get(key)
    const ttl = hit?.userId === null ? Math.min(this.cacheMs, 2000) : this.cacheMs
    if (hit && at - hit.at < ttl) return hit.userId ? { userId: hit.userId, credential } : null
    let response: Response
    try {
      response = await this.fetchImpl(`${this.apiBaseUrl}/me`, {
        headers: { accept: 'application/json', ...credentialHeaders(credential) },
        signal: AbortSignal.timeout(5000),
        redirect: 'manual',
      })
    } catch (error) {
      throw new ApiUnavailable(`identity service unreachable: ${(error as Error).name}`)
    }
    if (response.status === 401 || response.status === 403) {
      this.remember(key, null, at)
      return null
    }
    if (!response.ok) throw new ApiUnavailable(`identity service answered HTTP ${response.status}`)
    const body = await response.json().catch(() => null) as { user?: { id?: unknown } } | null
    const userId = body?.user?.id
    if (typeof userId !== 'string' || !userId || userId.length > 64) throw new ApiUnavailable('identity service returned no user id')
    this.remember(key, userId, at)
    return { userId, credential }
  }

  private remember(key: string, userId: string | null, at: number): void {
    if (this.cache.size > 10_000) this.cache.clear()
    this.cache.set(key, { userId, at })
  }
}
