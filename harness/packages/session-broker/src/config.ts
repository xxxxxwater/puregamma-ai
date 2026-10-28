import path from 'node:path'
import process from 'node:process'

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
}

const bool = (value: string | undefined) => value?.toLowerCase() === 'true'
const int = (value: string | undefined, fallback: number, min: number, max: number) => {
  const parsed = Number.parseInt(value ?? '', 10)
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : fallback
}
const list = (value: string | undefined) => (value ?? '').split(',').map(item => item.trim()).filter(Boolean)

/** Names that must never reach a Host even if listed for passthrough. */
export const NEVER_PASSED = new Set(['PUREGAMMA_LEGACY_API_TOKEN', 'DSH_BROKER_SECRET', 'PUREGAMMA_DSH_BROKER_SECRET', 'JWT_SECRET', 'SESSION_SECRET', 'INTERNAL_RUNTIME_SECRET'])

export function loadConfig(env: NodeJS.ProcessEnv = process.env): BrokerConfig {
  const profileDir = path.resolve(env.PUREGAMMA_DSH_PROFILE_DIR ?? path.join(import.meta.dirname, '..', '..', '..', 'profile'))
  const apiBaseUrl = (env.PUREGAMMA_LEGACY_API_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, '')
  return {
    enabled: bool(env.PUREGAMMA_DSH_BROKER_ENABLED),
    listenHost: env.PUREGAMMA_DSH_BROKER_HOST ?? '127.0.0.1',
    listenPort: int(env.PUREGAMMA_DSH_BROKER_PORT, 3480, 0, 65535),
    publicOrigin: (env.PUREGAMMA_DSH_PUBLIC_ORIGIN ?? 'http://127.0.0.1:3480').replace(/\/+$/, ''),
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
  return errors
}
