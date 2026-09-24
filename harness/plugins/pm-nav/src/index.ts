import { readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { Service } from '@deepseek-ai/cordis'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@puregamma/dsh-auth'
import {
  BUNDLE_NOT_FOUND,
  LATEST_SCHEMA,
  MAX_CACHE_SECONDS,
  SERIES_SCHEMA,
  STALE_AFTER_SECONDS,
  accountView,
  isAllowedEmail,
  navHistoryView,
  parseAllowedEmails,
  parseBundle,
  unreadableBundle,
  type BundleRead,
  type PmAccountView,
  type PmNavHistoryView,
} from './policy.ts'

export * from './policy.ts'

/** The single reason a caller is refused; mirrors the classic 403 code. */
export const PM_ACCOUNT_NOT_AUTHORIZED = 'PM_ACCOUNT_NOT_AUTHORIZED'

export interface Config {
  /** Directory riskbot publishes into. Must be mounted read-only in production. */
  riskbotExportDir?: string
  /** Comma/semicolon separated allowlist. Empty means deny everyone. */
  allowedEmails?: string
  accountLabel?: string
}

export const Config: z<Config> = z.object({
  riskbotExportDir: z.string().default('/var/lib/puregamma/riskbot'),
  allowedEmails: z.string().default(''),
  accountLabel: z.string().default('Binance Portfolio Margin'),
})

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgPmNav: PmNavService
  }
}

/**
 * PureGamma private PM account seam.
 *
 * Read-only by construction: the only data source is a directory of files the
 * independent riskbot collector writes. No implementation may hold an exchange
 * credential for this account, and no method here mutates anything.
 *
 * Every read resolves the requester from the authenticated session
 * (`pgAuth.currentUser()`) and evaluates the allowlist server-side. No method
 * accepts an identity, an allowlist or an "already authorized" flag from a
 * caller: visibility in the web client is not an authorization control.
 */
export abstract class PmNavService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgPmNav')
  }

  /** The configured allowlist, normalized. Empty ⇒ nobody is authorized. */
  abstract allowedEmails(): readonly string[]
  abstract account(): Promise<PmAccountView>
  abstract navHistory(): Promise<PmNavHistoryView>
}

interface CacheEntry {
  mtimeMs: number
  size: number
  readAtMs: number
  read: BundleRead
}

interface BundleReadResult {
  read: BundleRead
  mtimeMs: number | null
}

/**
 * Read-only bundle reader with a short stat-keyed cache.
 *
 * Files are addressed by fixed constants, never by caller input, so there is no
 * path-traversal surface. A read that fails keeps the previous good copy only
 * while it is still inside the staleness window; beyond that the outage is
 * reported instead of a stale page presented as live.
 */
export class RiskbotBundleReader {
  constructor(
    private readonly directory: string,
    private readonly now: () => number = Date.now,
  ) {}

  private readonly cache = new Map<string, CacheEntry>()

  async read(filename: string, schema: string): Promise<BundleReadResult> {
    const path = join(this.directory, filename)
    const entry = this.cache.get(filename)
    let info
    try {
      info = await stat(path)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        if (entry !== undefined && (this.now() - entry.readAtMs) / 1000 <= STALE_AFTER_SECONDS) {
          return { read: entry.read, mtimeMs: entry.mtimeMs }
        }
        return { read: { ok: false, error: BUNDLE_NOT_FOUND }, mtimeMs: null }
      }
      return { read: { ok: false, error: unreadableBundle(error) }, mtimeMs: null }
    }
    if (
      entry !== undefined
      && entry.mtimeMs === info.mtimeMs
      && entry.size === info.size
      && (this.now() - entry.readAtMs) / 1000 < MAX_CACHE_SECONDS
    ) {
      return { read: entry.read, mtimeMs: entry.mtimeMs }
    }

    let read: BundleRead
    try {
      read = parseBundle(await readFile(path, 'utf8'), schema)
    } catch (error) {
      read = { ok: false, error: unreadableBundle(error) }
    }
    // Only a good read replaces the cache, so the last good copy stays available
    // to the missing-file fallback above.
    if (read.ok) this.cache.set(filename, { mtimeMs: info.mtimeMs, size: info.size, readAtMs: this.now(), read })
    return { read, mtimeMs: info.mtimeMs }
  }
}

/**
 * riskbot-bundle provider. This is the production implementation, not a
 * compatibility bridge: PureGamma reads the collector's files directly and
 * holds no Binance credential for this account.
 */
export class RiskbotPmNavProvider extends PmNavService {
  static Config = Config

  private readonly directory: string
  private readonly allowed: readonly string[]
  private readonly label: string
  private readonly reader: RiskbotBundleReader

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.directory = config.riskbotExportDir ?? process.env.PM_RISKBOT_EXPORT_DIR ?? '/var/lib/puregamma/riskbot'
    this.allowed = parseAllowedEmails(config.allowedEmails ?? process.env.PM_ACCOUNT_ALLOWED_EMAILS ?? '')
    this.label = config.accountLabel ?? process.env.PM_ACCOUNT_LABEL ?? 'Binance Portfolio Margin'
    this.reader = new RiskbotBundleReader(this.directory)
  }

  allowedEmails(): readonly string[] {
    return this.allowed
  }

  /**
   * Resolve the authenticated identity and evaluate the allowlist.
   *
   * Returns the refusal reason, or undefined when the caller may read. Every
   * failure mode — no auth capability, no session, an unconfigured allowlist —
   * denies.
   */
  private async authorizationFailure(): Promise<string | undefined> {
    const auth = this.ctx.get('pgAuth')
    if (auth === undefined) return PM_ACCOUNT_NOT_AUTHORIZED
    let email: string
    try {
      email = (await auth.currentUser()).email
    } catch {
      return PM_ACCOUNT_NOT_AUTHORIZED
    }
    return isAllowedEmail(email, this.allowed) ? undefined : PM_ACCOUNT_NOT_AUTHORIZED
  }

  async account(): Promise<PmAccountView> {
    const refusal = await this.authorizationFailure()
    const bundlePath = join(this.directory, 'latest.json')
    if (refusal !== undefined) {
      // Never touch the bundle for an unauthorized caller.
      return accountView({ read: { ok: false, error: refusal }, bundlePath, label: this.label, observedAtMs: null, nowMs: Date.now() })
    }
    const { read, mtimeMs } = await this.reader.read('latest.json', LATEST_SCHEMA)
    return accountView({ read, bundlePath, label: this.label, observedAtMs: mtimeMs, nowMs: Date.now() })
  }

  async navHistory(): Promise<PmNavHistoryView> {
    const refusal = await this.authorizationFailure()
    if (refusal !== undefined) return navHistoryView({ ok: false, error: refusal })
    const { read } = await this.reader.read('series.json', SERIES_SCHEMA)
    return navHistoryView(read)
  }
}

export default RiskbotPmNavProvider
