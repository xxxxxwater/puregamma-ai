import { spawn, type ChildProcess } from 'node:child_process'
import { createHash } from 'node:crypto'
import { promises as fs } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import process from 'node:process'
import { NEVER_PASSED, type BrokerConfig } from './config.ts'
import type { UserCredential } from './identity.ts'
import { TokenKeeper } from './tokens.ts'

/** One user's running DSH Web Host. */
export interface Host {
  readonly userId: string
  readonly port: number
  /** `name=value` of the Host's browser-session cookie, held by the broker only. */
  readonly cookie: string
  lastActive: number
  openSockets: number
}

interface Record_ {
  host?: Host
  starting?: Promise<Host>
  child?: ChildProcess
  tokens: TokenKeeper
}

export class CapacityError extends Error {}

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

  constructor(
    private readonly config: BrokerConfig,
    private readonly log: (message: string) => void = message => console.error(`[dsh-broker] ${message}`),
    private readonly fetchImpl: typeof fetch = fetch,
  ) {
    this.reaper = setInterval(() => void this.reap(), Math.min(60_000, Math.max(1000, config.idleMs / 4)))
    this.reaper.unref()
  }

  get size(): number { return this.records.size }

  /** Counts only; never user ids. */
  stats(): { hosts: number; openSockets: number } {
    let openSockets = 0
    for (const record of this.records.values()) openSockets += record.host?.openSockets ?? 0
    return { hosts: this.records.size, openSockets }
  }

  /** Running Host for the user, starting it (and seeding its token) on first use. */
  async acquire(userId: string, credential: UserCredential): Promise<Host> {
    let record = this.records.get(userId)
    if (!record) {
      if (this.records.size >= this.config.maxHosts) await this.reap(true)
      if (this.records.size >= this.config.maxHosts) throw new CapacityError('all Host slots are in use')
      const paths = hostPaths(this.config.hostsRoot, userId)
      record = { tokens: new TokenKeeper(userId, paths.tokenFile, this.config.apiBaseUrl, this.config.brokerSecret, this.config.publicOrigin, this.fetchImpl, this.log) }
      this.records.set(userId, record)
    }
    try {
      await prepareDirs(hostPaths(this.config.hostsRoot, userId), this.config)
      await record.tokens.ensure(credential)
      if (record.host) {
        record.host.lastActive = Date.now()
        return record.host
      }
      record.starting ??= this.start(userId, record)
      const host = await record.starting
      host.lastActive = Date.now()
      return host
    } catch (error) {
      if (!record.host) await this.stop(userId)
      throw error
    }
  }

  private async start(userId: string, record: Record_): Promise<Host> {
    const paths = hostPaths(this.config.hostsRoot, userId)
    const args = [this.config.dshBin, this.config.profileName]
    for (const patch of this.config.patchFiles) args.push('--patch', patch)
    args.push('--port', '0', '--no-open')
    const child = spawn(process.execPath, args, { cwd: paths.workspace, env: hostEnv(this.config, paths), stdio: ['ignore', 'pipe', 'pipe'] })
    record.child = child
    child.once('exit', (code, signal) => {
      this.log(`host ${userKey(userId)} exited (${signal ?? code})`)
      if (this.records.get(userId)?.child === child) void this.stop(userId)
    })
    child.stderr?.on('data', chunk => process.env.PUREGAMMA_DSH_BROKER_DEBUG === 'true' && process.stderr.write(chunk))
    const ready = await new Promise<{ port: number; url: string }>((resolve, reject) => {
      let buffer = ''
      const timer = setTimeout(() => reject(new Error('Host did not become ready in time')), this.config.startTimeoutMs)
      child.stdout?.on('data', chunk => {
        buffer += String(chunk)
        if (buffer.length > 65536) buffer = buffer.slice(-65536)
        const match = READY.exec(buffer)
        if (match) {
          clearTimeout(timer)
          resolve({ url: match[1], port: Number(match[2]) })
        }
      })
      child.once('exit', () => { clearTimeout(timer); reject(new Error('Host exited before it was ready')) })
    })
    const cookie = await exchangeLaunchToken(ready.url, ready.port)
    const host: Host = { userId, port: ready.port, cookie, lastActive: Date.now(), openSockets: 0 }
    record.host = host
    record.starting = undefined
    this.log(`host ${userKey(userId)} ready on 127.0.0.1:${ready.port}`)
    return host
  }

  /** Stop Hosts idle past `idleMs` (or, under pressure, the least recently used idle one). */
  async reap(pressure = false): Promise<void> {
    const now = Date.now()
    const idle = [...this.records.values()]
      .filter(record => record.host && record.host.openSockets === 0)
      .sort((a, b) => a.host!.lastActive - b.host!.lastActive)
    for (const record of idle) {
      if (now - record.host!.lastActive >= this.config.idleMs) await this.stop(record.host!.userId)
    }
    if (pressure && this.records.size >= this.config.maxHosts && idle[0]?.host && this.records.has(idle[0].host.userId)) {
      await this.stop(idle[0].host.userId)
    }
  }

  async stop(userId: string): Promise<void> {
    const record = this.records.get(userId)
    if (!record) return
    this.records.delete(userId)
    await record.tokens.close()
    const child = record.child
    if (child && child.exitCode === null && child.signalCode === null) {
      child.kill('SIGTERM')
      const killer = setTimeout(() => child.kill('SIGKILL'), 5000)
      killer.unref()
      child.once('exit', () => clearTimeout(killer))
    }
  }

  async close(): Promise<void> {
    clearInterval(this.reaper)
    await Promise.all([...this.records.keys()].map(userId => this.stop(userId)))
  }
}

async function prepareDirs(paths: HostPaths, config: BrokerConfig): Promise<void> {
  await fs.mkdir(config.hostsRoot, { recursive: true, mode: 0o700 })
  for (const dir of [paths.dir, paths.home, paths.workspace, path.join(paths.home, 'profiles')]) {
    await fs.mkdir(dir, { recursive: true, mode: 0o700 })
  }
  const link = path.join(paths.home, 'profiles', config.profileName)
  const current = await fs.readlink(link).catch(() => undefined)
  if (current !== config.profileDir) {
    await fs.rm(link, { force: true, recursive: false }).catch(() => {})
    await fs.symlink(config.profileDir, link, 'dir')
  }
}

/**
 * Trade the one-time launch token for the Host's browser-session cookie, as
 * the browser would: `GET /?token=` with the Host's own loopback authority.
 * The cookie stays in the broker; the browser never sees the token or cookie.
 */
export function exchangeLaunchToken(url: string, port: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { headers: { host: `127.0.0.1:${port}` }, timeout: 10_000 }, response => {
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
