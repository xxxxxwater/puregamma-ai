import { userInfo } from 'node:os'
import path from 'node:path'
import process from 'node:process'
import type { LauncherKind } from './launchers.ts'

/**
 * Broker configuration. Everything defaults to the safe side: the broker
 * refuses to start unless explicitly enabled, listens on loopback, and runs
 * few Hosts that are reaped quickly.
 */
export interface BrokerConfig {
  /** Feature flag. `false` means the broker never listens. */
  enabled: boolean
  listenHost: string
  listenPort: number
  /** Public origin users reach the broker at (scheme://host[:port]); the only accepted Origin. */
  publicOrigin: string
  /**
   * URL path the broker is mounted under, e.g. `/harness` ('' = origin root).
   * DSH Web only emits relative URLs (`<base href="./">`, `api/remote.mux`
   * resolved against `document.baseURI`), so a prefix works; the recommended
   * production layout is still a dedicated subdomain at the root (see
   * docs/architecture/upgrade-20261029/dsh-ingress-isolation.md).
   */
  basePath: string
  /** Content-Security-Policy put on every response ('' = none). */
  contentSecurityPolicy: string
  /** Where an unauthenticated browser navigation is pointed (optional link in the 401 page). */
  loginUrl: string
  /** FastAPI base URL used for `GET /me` and the Host token mint. */
  apiBaseUrl: string
  /** Service secret for `POST /internal/dsh/host-tokens`. */
  brokerSecret: string
  /** PureGamma session cookie name; the only cookie forwarded to FastAPI. */
  sessionCookieName: string
  /** Per-user state root; each user gets `<root>/<sha256(userId)[0:32]>`. */
  hostsRoot: string
  /** Absolute path of the DSH launcher (`@deepseek-ai/dsh/lib/bin.js`). */
  dshBin: string
  /** The PureGamma profile directory linked into each Host's DSH_HOME. */
  profileDir: string
  /** Profile name under `$DSH_HOME/profiles`. */
  profileName: string
  /** Multi-tenant overlay passed to the launcher with `--patch`. */
  patchFiles: string[]
  maxHosts: number
  idleMs: number
  startTimeoutMs: number
  authCacheMs: number
  /** Extra environment names copied into Hosts (model provider keys, etc.). */
  envPassthrough: string[]
  /** Base URL Hosts use for FastAPI (defaults to apiBaseUrl). */
  hostApiBaseUrl: string
  /** V8 old-space cap per Host process, in MB. */
  hostHeapMb: number
  /** How Hosts are started (see launchers.ts). `direct` keeps the v0.3.3 behaviour. */
  launcher: LauncherKind
  /** Names this broker's units/containers so a restart sweeps only its own leftovers. */
  instance: string
  /** Kernel-enforced per-Host limits (systemd/docker launchers; `direct` only applies the heap cap). */
  hostLimits: HostLimits
  /** Per-user directory quota in MB (all launchers; enforced by the broker's size check). */
  diskQuotaMb: number
  diskCheckMs: number
  /** Extra read-only paths a sandboxed Host may see. */
  sandboxReadOnlyPaths: string[]
  /** Roots hidden from a systemd-sandboxed Host (replaced by an empty read-only tmpfs). */
  sandboxHide: string[]
  dockerBin: string
  dockerImage: string
  /** Node inside the image. */
  dockerNode: string
  dockerNetwork: string
  /** `uid:gid` the container runs as; defaults to the broker's own, so it can read the 0600 token file. */
  dockerUser: string
  dockerAddHosts: string[]
  /** Absolute path of container-entry.mjs (inside a read-only mount). */
  containerEntry: string
}

export interface HostLimits {
  memoryMb: number
  cpuPercent: number
  tasksMax: number
  nofile: number
  /** RLIMIT_FSIZE: no single file a Host writes can exceed this. */
  fileSizeMb: number
}

const bool = (value: string | undefined) => value?.toLowerCase() === 'true'
const int = (value: string | undefined, fallback: number, min: number, max: number) => {
  const parsed = Number.parseInt(value ?? '', 10)
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : fallback
}
const list = (value: string | undefined) => (value ?? '').split(',').map(item => item.trim()).filter(Boolean)

/** Names that must never reach a Host even if listed for passthrough. */
export const NEVER_PASSED = new Set(['PUREGAMMA_LEGACY_API_TOKEN', 'DSH_BROKER_SECRET', 'PUREGAMMA_DSH_BROKER_SECRET', 'JWT_SECRET', 'SESSION_SECRET', 'INTERNAL_RUNTIME_SECRET'])

/**
 * DSH Web boots from inline scripts whose content changes with every plugin
 * revision, so script hashes are not stable, and its Cordis client loader
 * builds an evaluator for `!!js` config expressions with `new Function` when
 * the shell module loads (0.1.7: the shell stays blank without
 * 'unsafe-eval'). Scripts still come only from the broker's own origin; no
 * third-party origin is allowed anywhere. `frame-ancestors 'none'` keeps the
 * Session UI out of other sites' frames.
 */
export function defaultContentSecurityPolicy(publicOrigin: string): string {
  let socket = ''
  try {
    const url = new URL(publicOrigin)
    socket = ` ${url.protocol === 'https:' ? 'wss:' : 'ws:'}//${url.host}`
  } catch {}
  return [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self'${socket}`,
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join('; ')
}

const normalizeBasePath = (value: string | undefined) => (value ?? '').trim().replace(/\/+$/, '')

export function loadConfig(env: NodeJS.ProcessEnv = process.env): BrokerConfig {
  const profileDir = path.resolve(env.PUREGAMMA_DSH_PROFILE_DIR ?? path.join(import.meta.dirname, '..', '..', '..', 'profile'))
  const publicOrigin = (env.PUREGAMMA_DSH_PUBLIC_ORIGIN ?? 'http://127.0.0.1:3480').replace(/\/+$/, '')
  const hostHeapMb = int(env.PUREGAMMA_DSH_HOST_HEAP_MB, 1024, 256, 8192)
  const apiBaseUrl = (env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, '')
  return {
    enabled: bool(env.PUREGAMMA_DSH_BROKER_ENABLED),
    listenHost: env.PUREGAMMA_DSH_BROKER_HOST ?? '127.0.0.1',
    listenPort: int(env.PUREGAMMA_DSH_BROKER_PORT, 3480, 0, 65535),
    publicOrigin,
    basePath: normalizeBasePath(env.PUREGAMMA_DSH_BASE_PATH),
    contentSecurityPolicy: env.PUREGAMMA_DSH_CSP ?? defaultContentSecurityPolicy(publicOrigin),
    loginUrl: env.PUREGAMMA_DSH_LOGIN_URL ?? '',
    apiBaseUrl,
    brokerSecret: env.PUREGAMMA_DSH_BROKER_SECRET ?? '',
    sessionCookieName: env.PUREGAMMA_SESSION_COOKIE_NAME ?? 'pg_session',
    hostsRoot: path.resolve(env.PUREGAMMA_DSH_HOSTS_ROOT ?? path.join(process.cwd(), '.dsh-hosts')),
    dshBin: env.PUREGAMMA_DSH_BIN ?? '',
    profileDir,
    profileName: env.PUREGAMMA_DSH_PROFILE_NAME ?? 'puregamma',
    patchFiles: env.PUREGAMMA_DSH_PATCH ? list(env.PUREGAMMA_DSH_PATCH) : [path.join(profileDir, 'multi-tenant.patch.yml')],
    maxHosts: int(env.PUREGAMMA_DSH_MAX_HOSTS, 8, 1, 256),
    idleMs: int(env.PUREGAMMA_DSH_IDLE_MS, 15 * 60_000, 10_000, 24 * 3_600_000),
    startTimeoutMs: int(env.PUREGAMMA_DSH_START_TIMEOUT_MS, 60_000, 1_000, 600_000),
    authCacheMs: int(env.PUREGAMMA_DSH_AUTH_CACHE_MS, 15_000, 0, 60_000),
    envPassthrough: list(env.PUREGAMMA_DSH_HOST_ENV_PASSTHROUGH).filter(name => !NEVER_PASSED.has(name)),
    hostApiBaseUrl: (env.PUREGAMMA_DSH_HOST_API_URL ?? apiBaseUrl).replace(/\/+$/, ''),
    hostHeapMb,
    launcher: (['direct', 'systemd', 'docker'] as const).find(kind => kind === env.PUREGAMMA_DSH_HOST_LAUNCHER) ?? (env.PUREGAMMA_DSH_HOST_LAUNCHER ? 'invalid' as LauncherKind : 'direct'),
    instance: env.PUREGAMMA_DSH_INSTANCE ?? 'default',
    hostLimits: {
      memoryMb: int(env.PUREGAMMA_DSH_HOST_MEMORY_MB, hostHeapMb + 512, 256, 16384),
      cpuPercent: int(env.PUREGAMMA_DSH_HOST_CPU_PERCENT, 100, 10, 1600),
      tasksMax: int(env.PUREGAMMA_DSH_HOST_TASKS_MAX, 256, 16, 4096),
      nofile: int(env.PUREGAMMA_DSH_HOST_NOFILE, 4096, 256, 65536),
      fileSizeMb: int(env.PUREGAMMA_DSH_HOST_FILE_SIZE_MB, 256, 1, 16384),
    },
    diskQuotaMb: int(env.PUREGAMMA_DSH_HOST_DISK_MB, 1024, 16, 1_048_576),
    diskCheckMs: int(env.PUREGAMMA_DSH_HOST_DISK_CHECK_MS, 60_000, 1000, 3_600_000),
    sandboxReadOnlyPaths: list(env.PUREGAMMA_DSH_SANDBOX_RO_PATHS),
    sandboxHide: env.PUREGAMMA_DSH_SANDBOX_HIDE !== undefined ? list(env.PUREGAMMA_DSH_SANDBOX_HIDE) : ['/data', '/srv', '/mnt', '/media', '/opt'],
    dockerBin: env.PUREGAMMA_DSH_DOCKER_BIN ?? 'docker',
    dockerImage: env.PUREGAMMA_DSH_DOCKER_IMAGE ?? '',
    dockerNode: env.PUREGAMMA_DSH_DOCKER_NODE ?? 'node',
    dockerNetwork: env.PUREGAMMA_DSH_DOCKER_NETWORK ?? 'bridge',
    dockerUser: env.PUREGAMMA_DSH_DOCKER_USER ?? `${userInfo().uid}:${userInfo().gid}`,
    dockerAddHosts: list(env.PUREGAMMA_DSH_DOCKER_ADD_HOSTS),
    containerEntry: path.resolve(import.meta.dirname, '..', 'container-entry.mjs'),
  }
}

export function validateConfig(config: BrokerConfig): string[] {
  const errors: string[] = []
  if (!config.enabled) errors.push('PUREGAMMA_DSH_BROKER_ENABLED is not true; the multi-tenant broker is off by default')
  if (config.brokerSecret.length < 32) errors.push('PUREGAMMA_DSH_BROKER_SECRET must be at least 32 characters')
  if (!config.dshBin) errors.push('PUREGAMMA_DSH_BIN must point at the pinned DSH launcher (lib/bin.js)')
  try {
    const origin = new URL(config.publicOrigin)
    if (origin.origin !== config.publicOrigin) errors.push('PUREGAMMA_DSH_PUBLIC_ORIGIN must be a bare origin (scheme://host[:port])')
  } catch {
    errors.push('PUREGAMMA_DSH_PUBLIC_ORIGIN is not a URL')
  }
  if (!['direct', 'systemd', 'docker'].includes(config.launcher)) errors.push('PUREGAMMA_DSH_HOST_LAUNCHER must be direct, systemd or docker')
  if (!/^[a-z0-9-]{1,24}$/.test(config.instance)) errors.push('PUREGAMMA_DSH_INSTANCE must be 1-24 of [a-z0-9-]')
  if (config.launcher !== 'direct' && config.hostLimits.memoryMb < config.hostHeapMb + 128) {
    errors.push('PUREGAMMA_DSH_HOST_MEMORY_MB must leave at least 128 MB above PUREGAMMA_DSH_HOST_HEAP_MB')
  }
  if (config.launcher === 'docker' && !config.dockerImage) errors.push('PUREGAMMA_DSH_DOCKER_IMAGE is required for the docker launcher')
  if (config.launcher === 'docker' && !/^\d+:\d+$/.test(config.dockerUser)) errors.push('PUREGAMMA_DSH_DOCKER_USER must be uid:gid')
  if (config.launcher === 'systemd' && config.sandboxHide.some(dir => !path.isAbsolute(dir) || dir === '/')) errors.push('PUREGAMMA_DSH_SANDBOX_HIDE entries must be absolute and not /')
  if (config.basePath && !/^(\/[A-Za-z0-9._~-]+)+$/.test(config.basePath)) {
    errors.push('PUREGAMMA_DSH_BASE_PATH must look like /harness (no trailing slash, no query)')
  }
  if (config.loginUrl) {
    try {
      if (!/^https?:$/.test(new URL(config.loginUrl).protocol)) errors.push('PUREGAMMA_DSH_LOGIN_URL must be http(s)')
    } catch {
      errors.push('PUREGAMMA_DSH_LOGIN_URL is not a URL')
    }
  }
  return errors
}
