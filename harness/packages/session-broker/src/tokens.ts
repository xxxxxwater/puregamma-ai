import { promises as fs } from 'node:fs'
import path from 'node:path'
import { credentialHeaders, type UserCredential } from './identity.ts'

export interface MintedToken {
  token: string
  userId: string
  expiresAt: number
}

/**
 * Keeps one user's Host token file fresh. Tokens come from FastAPI's
 * `/internal/dsh/host-tokens`, which needs the broker secret plus a credential
 * of the same user; the response's `user_id` must equal the user this Host
 * serves or the token is discarded. Rotation uses the previous Host token, so
 * a Host keeps working between page loads until the API's re-auth horizon,
 * and the next authenticated request re-seeds it with the user's session.
 */
export class TokenKeeper {
  private current: MintedToken | undefined
  private timer: NodeJS.Timeout | undefined
  private closed = false

  constructor(
    readonly userId: string,
    readonly file: string,
    private readonly apiBaseUrl: string,
    private readonly brokerSecret: string,
    private readonly publicOrigin: string,
    private readonly fetchImpl: typeof fetch = fetch,
    private readonly log: (message: string) => void = () => {},
  ) {}

  /** Mint with the user's own credential unless the current token is still comfortably valid. */
  async ensure(credential: UserCredential): Promise<void> {
    const now = Math.floor(Date.now() / 1000)
    if (this.current && this.current.expiresAt - now > 120) return
    await this.mint(credentialHeaders(credential))
  }

  private async mint(auth: Record<string, string>): Promise<void> {
    const response = await this.fetchImpl(`${this.apiBaseUrl}/internal/dsh/host-tokens`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'application/json',
        'x-puregamma-broker-secret': this.brokerSecret,
        // FastAPI's cookie CSRF guard admits the site's own origin only.
        origin: this.publicOrigin,
        ...auth,
      },
      body: JSON.stringify({ expected_user_id: this.userId }),
      signal: AbortSignal.timeout(5000),
      redirect: 'manual',
    })
    if (!response.ok) throw new Error(`host token mint answered HTTP ${response.status}`)
    const body = await response.json() as { token?: unknown; user_id?: unknown; expires_at?: unknown }
    if (body.user_id !== this.userId || typeof body.token !== 'string' || typeof body.expires_at !== 'number') {
      throw new Error('host token mint returned a token for a different user or a malformed body')
    }
    if (this.closed) return
    this.current = { token: body.token, userId: body.user_id, expiresAt: body.expires_at }
    await writePrivate(this.file, `${body.token}\n`)
    this.schedule()
  }

  private schedule(): void {
    clearTimeout(this.timer)
    if (!this.current || this.closed) return
    const remainingMs = this.current.expiresAt * 1000 - Date.now()
    this.timer = setTimeout(() => {
      const token = this.current?.token
      if (!token) return
      this.mint({ authorization: `Bearer ${token}` }).catch(error => {
        // The token simply expires; providers then fail closed until the
        // user's next request re-seeds it.
        this.log(`host token rotation failed for one user: ${(error as Error).message}`)
      })
    }, Math.max(1000, remainingMs / 2))
    this.timer.unref()
  }

  async close(): Promise<void> {
    this.closed = true
    clearTimeout(this.timer)
    this.current = undefined
    await fs.rm(this.file, { force: true })
  }
}

/** Atomic 0600 write: the providers refuse group/world-readable token files. */
export async function writePrivate(file: string, content: string): Promise<void> {
  const tmp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.${Date.now()}.tmp`)
  await fs.writeFile(tmp, content, { mode: 0o600, flag: 'wx' })
  await fs.rename(tmp, file)
}
