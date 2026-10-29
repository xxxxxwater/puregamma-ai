import { spawn, type ChildProcess } from 'node:child_process'
import { createHash } from 'node:crypto'
import { promises as fs } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import process from 'node:process'
import { NEVER_PASSED, type BrokerConfig } from './config.ts'
import type { UserCredential } from './identity.ts'
import { createLauncher, type HostLauncher, type LaunchPlan } from './launchers.ts'
import { RateLimited, TokenBucket } from './limits.ts'
import { TokenKeeper } from './tokens.ts'

/** Host lifecycle notifications (for the audit log). Carries the user id; the listener hashes it. */
export interface HostEvent {
  action: 'start' | 'stop' | 'exit' | 'quota' | 'start-rate'
  userId: string
  reason?: string
  result: string
  ms?: number
}

/** One user's running DSH Web Host. */
export interface Host {
  readonly userId: string
  /** Loopback port the broker connects to. */
  readonly port: number
  /** `host:port` the Host's own fence expects in Host/Origin (differs from `port` for containers). */
  readonly authority: string
  /** `name=value` of the Host's browser-session cookie, held by the broker only. */
  readonly cookie: string
  lastActive: number
  openSockets: number
}

interface Record_ {
  host?: Host
  starting?: Promise<Host>
  child?: ChildProcess
  plan?: LaunchPlan
  prepared?: Promise<void>
  tokens: TokenKeeper
}

export class CapacityError extends Error {}
/** The user's directory is over `diskQuotaMb`: no Host runs until they are under it again. */
export class QuotaError extends Error {}

/**
 * Bytes allocated under `dir` (st_blocks, symlinks not followed), counted
 * until `stopAt` is exceeded or `maxEntries` are visited.
 */
export async function directoryUsage(dir: string, stopAt = Number.POSITIVE_INFINITY, maxEntries = 200_000): Promise<number> {
  let total = 0
  let visited = 0
  const stack = [dir]
  while (stack.length && total <= stopAt && visited < maxEntries) {
    const current = stack.pop()!
    const entries = await fs.readdir(current, { withFileTypes: true }).catch(() => [])
    for (const entry of entries) {
      visited += 1
      const full = path.join(current, entry.name)
      const stat = await fs.lstat(full).catch(() => undefined)
      if (!stat) continue
      total += stat.blocks * 512
      if (stat.isDirectory()) stack.push(full)
    }
  }
  return total
}

/** The launcher's ready line: `dsh web: http://127.0.0.1:<port>/?token=<token>`. */
const READY = /^dsh web: (http:\/\/127\.0\.0\.1:(\d+)\/\?token=([A-Za-z0-9_-]+))/m

/** Stable, path-safe directory name for a user id (ids never touch the filesystem). */
export function userKey(userId: string): string {
  return createHash('sha256').update(userId).digest('hex').slice(0, 32)
}

export interface HostPaths { dir: string; home: string; workspace: string; tokenFile: string }

export function hostPaths(root: string, userId: string): HostPaths {
  const dir = path.join(root, userKey(userId))
  return { dir, home: path.join(dir, 'home'), workspace: path.join(dir, 'workspace'), tokenFile: path.join(dir, 'legacy-api.token') }
}

/** Environment for a Host: an allowlist, never the broker's secrets or the shared legacy token. */
export function hostEnv(config: BrokerConfig, paths: HostPaths, source: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {}
  for (const name of ['PATH', 'LANG', 'LC_ALL', 'TZ', ...config.envPassthrough]) {
    if (!NEVER_PASSED.has(name) && source[name] !== undefined) env[name] = source[name]
  }
  return {
    ...env,
    HOME: paths.home,
    DSH_HOME: paths.home,
    NODE_ENV: 'production',
    NODE_OPTIONS: `--max-old-space-size=${config.hostHeapMb}`,
    PUREGAMMA_LEGACY_API_URL: config.hostApiBaseUrl,
    PUREGAMMA_LEGACY_API_TOKEN_FILE: paths.tokenFile,
    PUREGAMMA_DSH_WORKSPACE_ROOT: paths.workspace,
    // DSH's native-addon loader otherwise copies `.node` files into a cache
    // under os.tmpdir() and loads them from there: a writable executable
    // cache shared by every same-uid Host, and impossible on a noexec /tmp.
    // Load straight from the read-only install instead.
    NARB_DISABLE_NATIVE_CACHE: '1',
  }
}

/**
 * Maps each user to exactly one Host. Lookups are keyed by the user id FastAPI
 * returned for the request's own credential; there is no other route to a
 * Host, so one user's request can never reach another user's process.
 */
export class HostManager {
  private readonly records = new Map<string, Record_>()
  private readonly reaper: NodeJS.Timeout
  private readonly diskTimer: NodeJS.Timeout
  private readonly overQuota = new Set<string>()
  private readonly starts: TokenBucket
  readonly launcher: HostLauncher
  /** Resolves once Hosts left by an earlier run of this broker instance are gone. */
  readonly ready: Promise<void>

  constructor(
    private readonly config: BrokerConfig,
    private readonly log: (message: string) => void = message => console.error(`[dsh-broker] ${message}`),
    private readonly fetchImpl: typeof fetch = fetch,
    launcher?: HostLauncher,
    private readonly onEvent: (event: HostEvent) => void = () => {},
  ) {
    this.launcher = launcher ?? createLauncher(config)
    this.starts = new TokenBucket(config.limits.hostStartBurst, config.limits.hostStartsPerMin / 60)
    this.ready = this.launcher.sweep().then(count => { if (count) this.log(`removed ${count} stale ${this.launcher.kind} Host(s)`) }, () => {})
    this.reaper = setInterval(() => void this.reap(), Math.min(60_000, Math.max(1000, config.idleMs / 4)))
    this.reaper.unref()
    this.diskTimer = setInterval(() => void this.checkDisk(), config.diskCheckMs)
    this.diskTimer.unref()
  }

  private get quotaBytes(): number { return this.config.diskQuotaMb * 1024 * 1024 }

  /** Stop running Hosts whose user directory went over quota. Returns the stopped user keys. */
  async checkDisk(): Promise<string[]> {
    const stopped: string[] = []
    for (const [userId, record] of [...this.records]) {
      if (!record.host) continue
      const used = await directoryUsage(hostPaths(this.config.hostsRoot, userId).dir, this.quotaBytes)
      if (used > this.quotaBytes) {
        this.overQuota.add(userId)
        this.log(`host ${userKey(userId)} over disk quota (${Math.round(used / 1048576)} MB > ${this.config.diskQuotaMb} MB); stopping`)
        this.onEvent({ action: 'quota', userId, result: 'stopped' })
        await this.stop(userId, 'quota')
        stopped.push(userKey(userId))
      }
    }
    return stopped
  }

  get size(): number { return this.records.size }

  /** Counts only; never user ids. */
  stats(): { hosts: number; openSockets: number } {
    let openSockets = 0
    for (const record of this.records.values()) openSockets += record.host?.openSockets ?? 0
    return { hosts: this.records.size, openSockets }
  }

  /** Unit/container names of running Hosts, keyed by user key (never user ids). */
  launched(): Array<{ userKey: string; name: string }> {
    return [...this.records].filter(([, record]) => record.host).map(([userId, record]) => ({ userKey: userKey(userId), name: record.plan?.name ?? '' }))
  }

  /** Running Host for the user, starting it (and seeding its token) on first use. */
  async acquire(userId: string, credential: UserCredential, trace: Record<string, string> = {}): Promise<Host> {
    await this.ready
    let record = this.records.get(userId)
    if (!record) {
      const used = await directoryUsage(hostPaths(this.config.hostsRoot, userId).dir, this.quotaBytes)
      if (used > this.quotaBytes) {
        this.overQuota.add(userId)
        this.onEvent({ action: 'quota', userId, result: 'refused' })
        throw new QuotaError('user directory is over its disk quota')
      }
      this.overQuota.delete(userId)
      if (this.records.size >= this.config.maxHosts) await this.reap(true)
      // Another request for this user may have created the record meanwhile.
      record = this.records.get(userId)
    }
    if (!record) {
      if (this.records.size >= this.config.maxHosts) throw new CapacityError('all Host slots are in use')
      // Global budget for new Hosts: a burst of new users (or one user
      // cycling credentials) cannot fork-bomb the machine with DSH processes.
      const start = this.starts.take()
      if (!start.ok) {
        this.onEvent({ action: 'start-rate', userId, result: 'refused' })
        throw new RateLimited('host-start-rate', start.retryAfterSec)
      }
      const paths = hostPaths(this.config.hostsRoot, userId)
      record = { tokens: new TokenKeeper(userId, paths.tokenFile, this.config.apiBaseUrl, this.config.brokerSecret, this.config.publicOrigin, this.fetchImpl, this.log) }
      this.records.set(userId, record)
    }
    try {
      record.prepared ??= prepareDirs(hostPaths(this.config.hostsRoot, userId), this.config)
      await record.prepared
      await record.tokens.ensure(credential, trace)
      if (record.host) {
        record.host.lastActive = Date.now()
        return record.host
      }
      if (this.records.get(userId) !== record) throw new Error('Host was stopped while starting')
      if (!record.starting) {
        const began = Date.now()
        record.starting = this.start(userId, record)
        record.starting.then(
          () => this.onEvent({ action: 'start', userId, result: 'ok', ms: Date.now() - began }),
          error => this.onEvent({ action: 'start', userId, result: 'failed', reason: (error as Error).message.slice(0, 120), ms: Date.now() - began }),
        )
      }
      const host = await record.starting
      host.lastActive = Date.now()
      return host
    } catch (error) {
      if (!record.host && this.records.get(userId) === record) await this.stop(userId, 'start-failed')
      throw error
    }
  }

  private async start(userId: string, record: Record_): Promise<Host> {
    const paths = hostPaths(this.config.hostsRoot, userId)
    const dshArgs = [this.config.profileName]
    for (const patch of this.config.patchFiles) dshArgs.push('--patch', patch)
    dshArgs.push('--port', '0', '--no-open')
    const plan = this.launcher.plan({ userKey: userKey(userId), paths, env: hostEnv(this.config, paths), dshArgs })
    const child = spawn(plan.command, plan.args, { cwd: plan.cwd, env: plan.env, stdio: ['ignore', 'pipe', 'pipe'] })
    record.child = child
    record.plan = plan
    child.once('exit', (code, signal) => {
      this.log(`host ${userKey(userId)} exited (${signal ?? code})`)
      if (this.records.get(userId)?.child === child) {
        this.onEvent({ action: 'exit', userId, result: String(signal ?? code) })
        void this.stop(userId, 'exited')
      }
    })
    child.stderr?.on('data', chunk => process.env.PUREGAMMA_DSH_BROKER_DEBUG === 'true' && process.stderr.write(chunk))
    const ready = await new Promise<{ port: number; token: string }>((resolve, reject) => {
      let buffer = ''
      const timer = setTimeout(() => reject(new Error('Host did not become ready in time')), this.config.startTimeoutMs)
      child.stdout?.on('data', chunk => {
        buffer += String(chunk)
        if (buffer.length > 65536) buffer = buffer.slice(-65536)
        const match = READY.exec(buffer)
        if (match) {
          clearTimeout(timer)
          resolve({ port: Number(match[2]), token: match[3] })
        }
      })
      child.once('exit', () => { clearTimeout(timer); reject(new Error('Host exited before it was ready')) })
    })
    const target = await plan.connect(ready.port)
    const cookie = await exchangeLaunchToken(ready.token, target)
    const host: Host = { userId, port: target.port, authority: target.authority, cookie, lastActive: Date.now(), openSockets: 0 }
    record.host = host
    record.starting = undefined
    this.log(`host ${userKey(userId)} ready on 127.0.0.1:${target.port} (${this.launcher.kind})`)
    return host
  }

  /** Stop Hosts idle past `idleMs` (or, under pressure, the least recently used idle one). */
  async reap(pressure = false): Promise<void> {
    const now = Date.now()
    const idle = [...this.records.values()]
      .filter(record => record.host && record.host.openSockets === 0)
      .sort((a, b) => a.host!.lastActive - b.host!.lastActive)
    for (const record of idle) {
      if (now - record.host!.lastActive >= this.config.idleMs) await this.stop(record.host!.userId, 'idle')
    }
    if (pressure && this.records.size >= this.config.maxHosts && idle[0]?.host && this.records.has(idle[0].host.userId)) {
      await this.stop(idle[0].host.userId, 'capacity')
    }
  }

  async stop(userId: string, reason = 'requested'): Promise<void> {
    const record = this.records.get(userId)
    if (!record) return
    this.records.delete(userId)
    if (reason !== 'exited') this.onEvent({ action: 'stop', userId, reason, result: 'ok' })
    await record.tokens.close()
    await record.plan?.stop()
    const child = record.child
    if (child && child.exitCode === null && child.signalCode === null) {
      child.kill('SIGTERM')
      const killer = setTimeout(() => child.kill('SIGKILL'), 5000)
      killer.unref()
      child.once('exit', () => clearTimeout(killer))
    }
  }

  /** True when the user's last start or size check found the directory over quota. */
  isOverQuota(userId: string): boolean { return this.overQuota.has(userId) }

  async close(): Promise<void> {
    clearInterval(this.reaper)
    clearInterval(this.diskTimer)
    await Promise.all([...this.records.keys()].map(userId => this.stop(userId, 'shutdown')))
  }
}

/** Files DSH writes into the profile directory at boot (and its Loader may write back at runtime). */
const PROFILE_WRITABLE = new Set(['cordis.yml'])

async function prepareDirs(paths: HostPaths, config: BrokerConfig): Promise<void> {
  await fs.mkdir(config.hostsRoot, { recursive: true, mode: 0o700 })
  for (const dir of [paths.dir, paths.home, paths.workspace, path.join(paths.home, 'profiles')]) {
    // Never follow a link a Host planted in its own directory.
    const stat = await fs.lstat(dir).catch(() => undefined)
    if (stat && !stat.isDirectory()) await fs.rm(dir, { force: true })
    await fs.mkdir(dir, { recursive: true, mode: 0o700 })
  }
  await prepareProfile(path.join(paths.home, 'profiles', config.profileName), config.profileDir)
}

/**
 * Each Host gets its own profile directory: every entry of the shared
 * profile is linked in read-only, except the files DSH writes (the root
 * `cordis.yml`), which are private copies. Symlinking the whole profile, as
 * v0.3.3 did, made every Host rewrite one shared file in the repository, and
 * a sandboxed Host cannot write a read-only profile at all.
 */
export async function prepareProfile(dir: string, shared: string): Promise<void> {
  const stat = await fs.lstat(dir).catch(() => undefined)
  if (stat && !stat.isDirectory()) await fs.rm(dir, { force: true })
  await fs.mkdir(dir, { recursive: true, mode: 0o700 })
  const wanted = new Set(await fs.readdir(shared))
  for (const name of await fs.readdir(dir)) {
    if (!wanted.has(name)) await fs.rm(path.join(dir, name), { recursive: true, force: true })
  }
  for (const name of wanted) {
    const target = path.join(shared, name)
    const entry = path.join(dir, name)
    if (PROFILE_WRITABLE.has(name)) {
      const current = await fs.lstat(entry).catch(() => undefined)
      if (current?.isSymbolicLink()) await fs.rm(entry, { force: true })
      if (!current || current.isSymbolicLink()) await fs.copyFile(target, entry)
      await fs.chmod(entry, 0o600)
      continue
    }
    if (await fs.readlink(entry).catch(() => undefined) === target) continue
    await fs.rm(entry, { recursive: true, force: true })
    await fs.symlink(target, entry)
  }
}

/**
 * Trade the one-time launch token for the Host's browser-session cookie, as
 * the browser would: `GET /?token=` with the Host's own loopback authority.
 * The cookie stays in the broker; the browser never sees the token or cookie.
 */
export function exchangeLaunchToken(token: string, target: { port: number; authority: string }): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = http.get({ host: '127.0.0.1', port: target.port, path: `/?token=${encodeURIComponent(token)}`, headers: { host: target.authority }, timeout: 10_000 }, response => {
      response.resume()
      const cookies = response.headers['set-cookie'] ?? []
      const pair = cookies.map(cookie => cookie.split(';')[0]).find(cookie => cookie.startsWith('dsh-auth-'))
      if (response.statusCode !== 303 || !pair) reject(new Error(`launch token exchange answered HTTP ${response.statusCode}`))
      else resolve(pair)
    })
    request.on('timeout', () => request.destroy(new Error('launch token exchange timed out')))
    request.on('error', reject)
  })
}
