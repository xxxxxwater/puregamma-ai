/**
 * Pure, fail-closed policy for the self-hosted pocket-relay mobile-access panel.
 *
 * pocket-relay (apps/pocket-relay) is an independent service: a cloudflared tunnel
 * plus an 8-digit PIN that exposes the web app to a phone. PureGamma does not
 * own its state; this module only normalizes and authorizes what the relay
 * publishes over its `/rpc/*` surface.
 *
 * Two invariants live here:
 *
 * 1. **The private LAN segment never reaches a client.** The relay publishes it,
 *    but a cloud host has no home LAN and the address would leak the server.
 *    `normalizeStatus` strips it unconditionally, and the QR reader accepts the
 *    public kind only. A caller cannot opt back in.
 * 2. **Nothing is invented.** An unconfigured relay, an unreachable relay or an
 *    unexpected payload reports `available: false` with the reason; it never
 *    becomes a stopped tunnel with a blank PIN presented as real state.
 *
 * This module is free of Cordis, node:fs and network access so the invariants are
 * unit-testable directly.
 */

export const RELAY_NOT_CONFIGURED = 'POCKET_RELAY_URL is not configured'
export const RPC_TOKEN_ENV_HINT = 'POCKET_RPC_SECRET'
export const POCKET_RPC_TOKEN_HEADER = 'x-pocket-rpc-token'

/** The relay's PIN is exactly eight digits; the client may not relax this. */
export const PIN_PATTERN = /^[0-9]{8}$/

/** Kind of PIN the relay exposes. `lan` exists but is never reachable over SaaS. */
export type PocketPinKind = 'public' | 'lan'

export type JsonRecord = Record<string, unknown>

export function isJsonRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function record(value: unknown): JsonRecord {
  return isJsonRecord(value) ? value : {}
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

function bool(value: unknown): boolean {
  return value === true
}

// ------------------------------------------------------------------- transport

export function normalizeRelayBase(value: string | null | undefined): string | undefined {
  const trimmed = (value ?? '').trim().replace(/\/+$/, '')
  return trimmed.length === 0 ? undefined : trimmed
}

/** The relay path is a fixed constant chosen by this module, never caller input. */
export function rpcUrl(base: string, path: string, params: Record<string, string> = {}): string {
  const query = Object.entries(params)
    .filter(([, value]) => value.length > 0)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&')
  return `${base}/rpc/${path}${query.length === 0 ? '' : `?${query}`}`
}

export function isValidPin(value: string): boolean {
  return PIN_PATTERN.test(value)
}

/** The relay rejects a non-public QR kind; refuse it here rather than round-trip. */
export function isExposablePinKind(value: string): value is 'public' {
  return value === 'public'
}

export function unreachableRelay(error: unknown): string {
  return `pocket relay unreachable: ${error instanceof Error ? error.message : String(error)}`.slice(0, 200)
}

// ----------------------------------------------------------------------- views

export interface MobileAccessPublicTunnel {
  running: boolean
  url: string | null
  pin: string | null
  custom: boolean
  autoStart: boolean
  lastError: string | null
}

export interface MobileAccessStatusView {
  available: boolean
  reason?: string
  observedAt: string
  source: string
  /** Server-resolved: only an admin may change tunnel or PIN state. */
  isAdmin: boolean
  target?: string
  port?: number
  publicTunnel?: MobileAccessPublicTunnel
  restartRequiresRelogin?: boolean
}

const SOURCE = 'cordis:pgMobileAccess'

export function unavailableStatus(reason: string, isAdmin: boolean, observedAtMs: number): MobileAccessStatusView {
  return { available: false, reason, observedAt: new Date(observedAtMs).toISOString(), source: SOURCE, isAdmin }
}

/**
 * Normalize one `/rpc/status` payload for a browser.
 *
 * `isAdmin` is decided by the host from the authenticated session; the relay
 * knows nothing about PureGamma users and must never be trusted for it.
 */
export function normalizeStatus(payload: unknown, input: { isAdmin: boolean; observedAtMs: number }): MobileAccessStatusView {
  if (!isJsonRecord(payload)) {
    return unavailableStatus('pocket relay returned a non-object status payload', input.isAdmin, input.observedAtMs)
  }
  const tunnel = record(payload.public)
  const session = record(payload.session)
  const port = typeof payload.port === 'number' && Number.isFinite(payload.port) ? payload.port : undefined
  return {
    available: true,
    observedAt: new Date(input.observedAtMs).toISOString(),
    source: SOURCE,
    isAdmin: input.isAdmin,
    // The LAN segment is dropped here, not filtered by each caller.
    ...(text(payload.target) === null ? {} : { target: text(payload.target) as string }),
    ...(port === undefined ? {} : { port }),
    publicTunnel: {
      running: bool(tunnel.running),
      url: text(tunnel.url),
      pin: text(tunnel.pin),
      custom: bool(tunnel.custom),
      autoStart: bool(tunnel.auto_start),
      lastError: text(tunnel.last_error),
    },
    restartRequiresRelogin: bool(session.restart_requires_relogin),
  }
}

export interface MobileAccessMutation {
  ok: boolean
  observedAt: string
  source: string
  reason?: string
  running?: boolean
  url?: string | null
  pin?: string | null
  lastError?: string | null
}

export function mutationFailure(reason: string, observedAtMs: number): MobileAccessMutation {
  return { ok: false, reason, observedAt: new Date(observedAtMs).toISOString(), source: SOURCE }
}

/** A relay error body is surfaced as a refusal, never as a success with blanks. */
export function mutationFromRelay(payload: unknown, observedAtMs: number): MobileAccessMutation {
  if (!isJsonRecord(payload)) return mutationFailure('pocket relay returned a non-object payload', observedAtMs)
  const observedAt = new Date(observedAtMs).toISOString()
  const running = typeof payload.running === 'boolean' ? payload.running : undefined
  const url = text(payload.url)
  const pin = text(payload.pin)
  const lastError = text(payload.last_error)
  return {
    ok: true,
    observedAt,
    source: SOURCE,
    ...(running === undefined ? {} : { running }),
    ...(payload.url === undefined ? {} : { url }),
    ...(pin === null ? {} : { pin }),
    ...(payload.last_error === undefined ? {} : { lastError }),
  }
}

export interface MobileAccessQr {
  available: boolean
  reason?: string
  contentType?: string
  bytes?: Uint8Array
}

export function qrUnavailable(reason: string): MobileAccessQr {
  return { available: false, reason }
}

export function qrFromResponse(contentType: string | null, bytes: Uint8Array): MobileAccessQr {
  const media = (contentType ?? '').split(';', 1)[0].trim().toLowerCase()
  if (media !== 'image/png') return qrUnavailable('pocket relay did not return a PNG QR code')
  if (bytes.byteLength === 0) return qrUnavailable('pocket relay returned an empty QR code')
  return { available: true, contentType: media, bytes }
}
