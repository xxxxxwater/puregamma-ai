import { Service } from '@deepseek-ai/cordis'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@puregamma/dsh-auth'
import {
  POCKET_RPC_TOKEN_HEADER,
  RELAY_NOT_CONFIGURED,
  isValidPin,
  mutationFailure,
  mutationFromRelay,
  normalizeRelayBase,
  normalizeStatus,
  qrFromResponse,
  qrUnavailable,
  rpcUrl,
  unavailableStatus,
  unreachableRelay,
  type MobileAccessMutation,
  type MobileAccessQr,
  type MobileAccessStatusView,
  type PocketPinKind,
} from './policy.ts'

export * from './policy.ts'

/** The single reason a non-admin is refused a state change. */
export const MOBILE_ACCESS_ADMIN_REQUIRED = 'MOBILE_ACCESS_ADMIN_REQUIRED'

export interface Config {
  /** Base URL of the self-hosted pocket-relay. Empty means the capability is off. */
  relayUrl?: string
  /** Environment variable holding the relay RPC secret. */
  rpcSecretEnv?: string
  requestTimeoutMs?: number
}

export const Config: z<Config> = z.object({
  relayUrl: z.string().default(''),
  rpcSecretEnv: z.string().default('POCKET_RPC_SECRET'),
  requestTimeoutMs: z.number().min(100).max(60000).default(30000),
})

declare module '@deepseek-ai/cordis' {
  interface Context {
    pgMobileAccess: MobileAccessService
  }
}

/**
 * Mobile-access seam over the self-hosted pocket-relay.
 *
 * Trust model, enforced server-side on every call:
 *
 * - any signed-in user may READ status and the public QR code;
 * - only an admin may START/STOP the tunnel or change the PIN.
 *
 * The admin decision is resolved from the authenticated session inside the
 * implementation. No method takes a caller-supplied identity, role or
 * "already authorized" flag, because a client asserting its own role is not
 * authorization. The relay's RPC secret stays server-side and is never echoed
 * back in any view.
 */
export abstract class MobileAccessService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'pgMobileAccess')
  }

  /** Read-only status. `isAdmin` is resolved by the host, not by the relay. */
  abstract status(): Promise<MobileAccessStatusView>
  /** PNG QR code for the public tunnel URL. */
  abstract qr(): Promise<MobileAccessQr>
  /** Admin only. Starting the tunnel rotates the public PIN, as the relay does. */
  abstract startTunnel(): Promise<MobileAccessMutation>
  /** Admin only. */
  abstract stopTunnel(): Promise<MobileAccessMutation>
  /** Admin only. */
  abstract rotatePin(which: PocketPinKind): Promise<MobileAccessMutation>
  /** Admin only. Rejects anything that is not eight digits. */
  abstract setPin(which: PocketPinKind, pin: string): Promise<MobileAccessMutation>
}

/**
 * pocket-relay provider. The relay owns tunnel, QR and PIN state; this class is
 * an adapter plus the PureGamma authorization layer in front of it.
 *
 * It never caches a mutation result into a success it did not observe: a relay
 * that is unreachable, misconfigured or returning an unexpected payload produces
 * an explicit refusal.
 */
export class PocketRelayMobileAccessProvider extends MobileAccessService {
  static Config = Config

  private readonly base: string | undefined
  private readonly secretEnv: string
  private readonly timeoutMs: number
  private readonly controllers = new Set<AbortController>()

  constructor(ctx: Context, config: Config = {}) {
    super(ctx)
    this.base = normalizeRelayBase(config.relayUrl ?? process.env.POCKET_RELAY_URL ?? '')
    this.secretEnv = config.rpcSecretEnv ?? 'POCKET_RPC_SECRET'
    this.timeoutMs = config.requestTimeoutMs ?? 30000
    ctx.effect(() => () => {
      for (const controller of this.controllers) controller.abort()
      this.controllers.clear()
    }, 'pgMobileAccess.abort-inflight')
  }

  /** Resolve the requester's admin role from the authenticated session. */
  private async isAdmin(): Promise<boolean> {
    const auth = this.ctx.get('pgAuth')
    if (auth === undefined) return false
    try {
      return (await auth.currentUser()).role === 'admin'
    } catch {
      return false
    }
  }

  private headers(): Record<string, string> {
    const secret = process.env[this.secretEnv] ?? ''
    // An unset secret is sent as no header and the relay falls back to its own
    // host allowlist; PureGamma never invents a token.
    return secret.length === 0 ? {} : { [POCKET_RPC_TOKEN_HEADER]: secret }
  }

  private async call(method: 'GET' | 'POST', path: string, params: Record<string, string> = {}, body?: unknown): Promise<{ status: number; contentType: string | null; bytes: Uint8Array } | { failure: string }> {
    if (this.base === undefined) return { failure: RELAY_NOT_CONFIGURED }
    const controller = new AbortController()
    this.controllers.add(controller)
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const response = await fetch(rpcUrl(this.base, path, params), {
        method,
        signal: controller.signal,
        headers: {
          Accept: 'application/json, image/png',
          ...this.headers(),
          ...(body === undefined ? {} : { 'content-type': 'application/json' }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      })
      const buffer = new Uint8Array(await response.arrayBuffer())
      return { status: response.status, contentType: response.headers.get('content-type'), bytes: buffer }
    } catch (error) {
      return { failure: unreachableRelay(error) }
    } finally {
      clearTimeout(timer)
      this.controllers.delete(controller)
    }
  }

  private static json<Value>(call: { status: number; contentType: string | null; bytes: Uint8Array }): Value | undefined {
    if (call.status < 200 || call.status >= 300) return undefined
    try {
      return JSON.parse(new TextDecoder().decode(call.bytes)) as Value
    } catch {
      return undefined
    }
  }

  async status(): Promise<MobileAccessStatusView> {
    const admin = await this.isAdmin()
    const now = Date.now()
    if (this.base === undefined) return unavailableStatus(RELAY_NOT_CONFIGURED, admin, now)
    const call = await this.call('GET', 'status')
    if ('failure' in call) return unavailableStatus(call.failure, admin, now)
    if (call.status < 200 || call.status >= 300) {
      return unavailableStatus(`pocket relay status returned HTTP ${call.status}`, admin, now)
    }
    const payload = PocketRelayMobileAccessProvider.json<unknown>(call)
    if (payload === undefined) return unavailableStatus('pocket relay status was not valid JSON', admin, now)
    return normalizeStatus(payload, { isAdmin: admin, observedAtMs: now })
  }

  async qr(): Promise<MobileAccessQr> {
    if (this.base === undefined) return qrUnavailable(RELAY_NOT_CONFIGURED)
    // SaaS only ever exposes the public tunnel; the LAN kind is never requested.
    const call = await this.call('GET', 'qr', { kind: 'public' })
    if ('failure' in call) return qrUnavailable(call.failure)
    if (call.status < 200 || call.status >= 300) return qrUnavailable(`pocket relay QR returned HTTP ${call.status}`)
    return qrFromResponse(call.contentType, call.bytes)
  }

  /**
   * The single authorization guard for every state change.
   *
   * It runs before any input validation, so a non-admin cannot use error text to
   * learn what the relay would have accepted.
   */
  private async denyUnlessAdmin(): Promise<MobileAccessMutation | undefined> {
    if (!(await this.isAdmin())) return mutationFailure(MOBILE_ACCESS_ADMIN_REQUIRED, Date.now())
    if (this.base === undefined) return mutationFailure(RELAY_NOT_CONFIGURED, Date.now())
    return undefined
  }

  private async send(path: string, body?: unknown): Promise<MobileAccessMutation> {
    const now = Date.now()
    const call = await this.call('POST', path, {}, body)
    if ('failure' in call) return mutationFailure(call.failure, now)
    if (call.status < 200 || call.status >= 300) return mutationFailure(`pocket relay ${path} returned HTTP ${call.status}`, now)
    const payload = PocketRelayMobileAccessProvider.json<unknown>(call)
    if (payload === undefined) return mutationFailure(`pocket relay ${path} was not valid JSON`, now)
    return mutationFromRelay(payload, now)
  }

  async startTunnel(): Promise<MobileAccessMutation> {
    const denied = await this.denyUnlessAdmin()
    return denied ?? this.send('tunnel/start')
  }

  async stopTunnel(): Promise<MobileAccessMutation> {
    const denied = await this.denyUnlessAdmin()
    return denied ?? this.send('tunnel/stop')
  }

  async rotatePin(which: PocketPinKind): Promise<MobileAccessMutation> {
    const denied = await this.denyUnlessAdmin()
    if (denied !== undefined) return denied
    if (which !== 'public' && which !== 'lan') return mutationFailure(`unknown PIN kind ${JSON.stringify(which)}`, Date.now())
    return this.send('pin/rotate', { which })
  }

  async setPin(which: PocketPinKind, pin: string): Promise<MobileAccessMutation> {
    const denied = await this.denyUnlessAdmin()
    if (denied !== undefined) return denied
    if (!isValidPin(pin)) return mutationFailure('PIN must be exactly eight digits', Date.now())
    return this.send('pin/custom', { which, pin })
  }
}

export default PocketRelayMobileAccessProvider
